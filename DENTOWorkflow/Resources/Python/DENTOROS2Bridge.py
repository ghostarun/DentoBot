"""Thin SlicerROS2 adapter for DENTOBOT Step 6 simulation.

ROS 2 and MoveIt are owned by the desktop launcher. This module observes a
versioned readiness topic, creates MRML robot/control nodes, publishes simulated
joint positions, and requests plans. It never starts, kills, or shells into ROS.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, replace
from enum import Enum
from math import acos, ceil, cos, degrees, floor, isfinite, pi, radians, sin, sqrt
from typing import Mapping, Optional, Sequence, Tuple
from uuid import uuid4

ROS2_ROBOT_NAME = "dentobot"
ROS2_URDF_PARAM_NODE = "/dentobot_robot_state_publisher"
ROS2_URDF_PARAM_NAME = "robot_description"
ROS2_FIXED_FRAME = "base_link"
ROS2_TF_PREFIX = ""
ROS2_JOINT_STATES_TOPIC = "/joint_states"
ROS2_PLANNING_GROUP = "dentobot_arm"
ROS2_TOOL_TCP_LINK = "dentobot_drill_tip_provisional"
ROS2_SLICER_JOINT_COMMAND_TOPIC = "/dentobot/slicer_joint_positions"
ROS2_JOINT_COMMAND_STATUS_TOPIC = "/dentobot/joint_command_status"
ROS2_JOINT_COMMAND_STATUS_SCHEMA = "dentobot.joint_command_status.v1"
ROS2_TASK_GUARD_CONFIG_TOPIC = "/dentobot/task_guard_config"
ROS2_TASK_JOINT_COMMAND_TOPIC = "/dentobot/task_joint_command"
ROS2_TASK_JOINT_STATUS_TOPIC = "/dentobot/task_joint_status"
ROS2_TASK_GUARD_CONFIG_SCHEMA = "dentobot.task_guard_config.v2"
ROS2_TASK_JOINT_COMMAND_SCHEMA = "dentobot.task_joint_command.v2"
ROS2_TASK_JOINT_STATUS_SCHEMA = "dentobot.task_joint_status.v2"
ROS2_SIMULATION_STATUS_TOPIC = "/dentobot/simulation_status"
ROS2_SIMULATION_STATUS_SCHEMA = "dentobot.simulation_status.v1"
ROS2_DEFAULT_SLICER_NODE = "slicer"
ROS2_SLICER_JOINT_PUBLISH_INTERVAL_MS = 50
ROS2_TASK_GUARD_INITIAL_SEQUENCE = 1
ROS2_GUARD_MAX_REVOLUTE_STEP_RAD = 0.017453292519943295
ROS2_GUARD_MAX_PRISMATIC_STEP_M = 0.0005
ROS2_GUARD_PREVIEW_MAX_INTERPOLATION_SAMPLES = 4
ROS2_RESEARCH_MINIMUM_CLEARANCE_M = 0.001
ROS2_MOVEIT_PLANNING_SCENE_SETTLE_SEC = 0.75
ROS2_MOVEIT_JOINT_PLAN_ATTEMPTS = 3
ROS2_TASK_GUARD_SCENE_SYNC_TIMEOUT_SEC = 8.0
ROS2_CARTESIAN_EEF_STEP_ATTEMPTS_M = (0.001, 0.0005, 0.00025)
CARTESIAN_START_POSITION_TOLERANCE_MM = 0.25
CARTESIAN_START_ORIENTATION_TOLERANCE_DEG = 0.5
ROS2_MONITORED_STATE_TIMEOUT_SEC = 3.0
ROS2_MONITORED_REVOLUTE_TOLERANCE_RAD = 0.001
ROS2_MONITORED_PRISMATIC_TOLERANCE_M = 0.0001

ROS2_ROBOT_NODE_ATTRIBUTE = "DENTOBOT.Ros2RobotName"
ROS2_MOTION_ACTIVE_ATTRIBUTE = "DENTOBOT.Ros2MotionControlActive"
ROS2_SLICER_JOINT_PUBLISHER_ATTRIBUTE = "DENTOBOT.SlicerJointCommandPublisher"
ROS2_STATUS_SUBSCRIBER_ATTRIBUTE = "DENTOBOT.SimulationStatusSubscriber"
ROS2_JOINT_STATUS_SUBSCRIBER_ATTRIBUTE = "DENTOBOT.JointCommandStatusSubscriber"
ROS2_OBSTACLE_PROXY_ATTRIBUTE = "DENTOBOT.MoveItObstacleProxy"
ROS2_OBSTACLE_SOURCE_ATTRIBUTE = "DENTOBOT.MoveItObstacleSource"
ROS2_OBSTACLE_PUBLISHED_ID_ATTRIBUTE = "DENTOBOT.MoveItObstaclePublishedId"
ROS2_PHASE_PATH_ATTRIBUTE = "DENTOBOT.Step6PhasePlanPath"
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
ROS2_CONTINUOUS_REVOLUTE_JOINTS = frozenset(
    {
        "link-5_Revolute-5",
        "pneumatic_spindle-Copy_Revolute-6",
    }
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
    coordinate_frame: str = ROS2_FIXED_FRAME
    start_position_error_mm: Optional[float] = None
    start_orientation_error_deg: Optional[float] = None
    axial_roll_deg: float = 0.0
    eef_step_m: Optional[float] = None
    requested_path_length_mm: float = 0.0
    completed_distance_mm: float = 0.0
    last_valid_waypoint_index: int = -1
    first_invalid_requested_index: int = -1
    last_valid_joint_positions_si: Optional[dict[str, float]] = None
    first_invalid_ras_mm: Optional[tuple[float, float, float]] = None
    failure_classification: str = ""
    collision_aware_ik_at_first_invalid: Optional[bool] = None
    kinematics_only_ik_at_first_invalid: Optional[bool] = None
    first_invalid_joint_positions_si: Optional[dict[str, float]] = None
    first_invalid_collision_pairs: tuple[tuple[str, str], ...] = ()
    submitted_start_joint_positions_si: Optional[dict[str, float]] = None
    submitted_goal_joint_positions_si: Optional[dict[str, float]] = None
    requested_goal_joint_positions_si: Optional[dict[str, float]] = None
    monitored_start_joint_positions_si: Optional[dict[str, float]] = None
    per_joint_start_goal_delta: Optional[dict[str, float]] = None
    maximum_start_goal_delta: Optional[float] = None
    maximum_start_goal_delta_joint: str = ""
    raw_maximum_start_goal_delta: Optional[float] = None
    raw_maximum_start_goal_delta_joint: str = ""
    continuous_joint_wrap_adjustments: Optional[dict[str, float]] = None
    maximum_monitored_start_error: Optional[float] = None
    planner_start_source: str = ""
    native_planner_message: str = ""


@dataclass(frozen=True)
class JointSegmentDiagnostic:
    """Read-only collision evidence along one direct joint interpolation."""

    sample_count: int
    collision_found: bool
    first_collision_fraction: Optional[float] = None
    first_collision_pairs: tuple[tuple[str, str], ...] = ()
    message: str = ""


@dataclass(frozen=True)
class JointCommandStatus:
    accepted: bool
    reason: str
    requested_positions: tuple[float, ...] = ()
    accepted_positions: tuple[float, ...] = ()
    checked_samples: int = 0
    minimum_clearance_m: float = ROS2_RESEARCH_MINIMUM_CLEARANCE_M
    minimum_self_distance_m: Optional[float] = None
    minimum_world_distance_m: Optional[float] = None
    first_body: str = ""
    second_body: str = ""
    world_object_count: int = 0
    world_objects: tuple[dict[str, object], ...] = ()
    world_object_evidence_present: bool = False


@dataclass(frozen=True)
class TaskJointStatus:
    accepted: bool
    reason: str
    task_fingerprint: str = ""
    guard_session_id: str = ""
    phase: str = ""
    sequence: int = -1
    requested_positions: tuple[float, ...] = ()
    accepted_positions: tuple[float, ...] = ()
    checked_samples: int = 0
    corridor_ok: bool = False
    corridor_progress: Optional[float] = None
    corridor_distance_m: Optional[float] = None
    minimum_clearance_m: float = ROS2_RESEARCH_MINIMUM_CLEARANCE_M
    minimum_self_distance_m: Optional[float] = None
    minimum_world_distance_m: Optional[float] = None
    first_body: str = ""
    second_body: str = ""
    world_object_count: int = 0
    world_objects: tuple[dict[str, object], ...] = ()
    exploratory_tool_contact_suppressed: bool = False
    suppressed_tool_contact_sample_count: int = 0


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
_native_joint_positions = [0.0] * len(ROS2_JOINT_SI_ORDER)
_native_goal_transform = None
_task_config_publisher = None
_task_command_publisher = None
_task_status_subscriber = None
_task_status_observer = None
_last_task_status = None
_last_task_status_at = 0.0
_last_task_config_json = ""


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

    def world_objects() -> tuple[dict[str, object], ...]:
        records = data.get("world_objects", [])
        if not isinstance(records, list):
            raise ValueError("world_objects must be an array.")
        normalized = []
        for record in records:
            if not isinstance(record, dict) or not str(record.get("id") or ""):
                raise ValueError("Each world object must have an ID.")
            pose = tuple(float(value) for value in record.get("pose_base_link_m_xyzw", ()))
            if len(pose) != 7 or not all(isfinite(value) for value in pose):
                raise ValueError("World-object pose must contain seven finite values.")
            bounds_data = record.get("bounds_base_link_m")
            bounds = None
            if bounds_data is not None:
                bounds = tuple(float(value) for value in bounds_data)
                if len(bounds) != 6 or not all(isfinite(value) for value in bounds):
                    raise ValueError("World-object bounds must contain six finite values.")
            normalized.append(
                {
                    "id": str(record["id"]),
                    "shape_count": max(0, int(record.get("shape_count", 0))),
                    "pose_base_link_m_xyzw": pose,
                    "bounds_base_link_m": bounds,
                }
            )
        return tuple(normalized)

    if not isinstance(data.get("accepted"), bool):
        raise ValueError("accepted must be a boolean.")
    minimum_clearance_m = float(
        data.get("minimum_clearance_m", ROS2_RESEARCH_MINIMUM_CLEARANCE_M)
    )
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
        world_objects=world_objects(),
        world_object_evidence_present="world_objects" in data,
    )


def parse_task_joint_status(payload: str) -> TaskJointStatus:
    data = json.loads(payload)
    if data.get("schema") != ROS2_TASK_JOINT_STATUS_SCHEMA:
        raise ValueError("Unsupported task-joint status schema.")
    if data.get("mode") != "simulation_only":
        raise ValueError("Task-joint status is not simulation-only.")

    def positions(key: str) -> tuple[float, ...]:
        values = tuple(float(value) for value in data.get(key, ()))
        if values and (
            len(values) != len(ROS2_JOINT_SI_ORDER)
            or not all(isfinite(value) for value in values)
        ):
            raise ValueError(f"{key} must contain six finite values.")
        return values

    def optional_number(key: str) -> Optional[float]:
        value = data.get(key)
        if value is None:
            return None
        result = float(value)
        if not isfinite(result):
            raise ValueError(f"{key} must be finite or null.")
        return result

    def world_objects() -> tuple[dict[str, object], ...]:
        records = data.get("world_objects", [])
        if not isinstance(records, list):
            raise ValueError("world_objects must be an array.")
        normalized = []
        for record in records:
            if not isinstance(record, dict) or not str(record.get("id") or ""):
                raise ValueError("Each world object must have an ID.")
            pose = tuple(float(value) for value in record.get("pose_base_link_m_xyzw", ()))
            bounds_data = record.get("bounds_base_link_m")
            bounds = None if bounds_data is None else tuple(float(value) for value in bounds_data)
            if len(pose) != 7 or not all(isfinite(value) for value in pose):
                raise ValueError("World-object pose must contain seven finite values.")
            if bounds is not None and (
                len(bounds) != 6 or not all(isfinite(value) for value in bounds)
            ):
                raise ValueError("World-object bounds must contain six finite values.")
            normalized.append(
                {
                    "id": str(record["id"]),
                    "shape_count": max(0, int(record.get("shape_count", 0))),
                    "pose_base_link_m_xyzw": pose,
                    "bounds_base_link_m": bounds,
                }
            )
        return tuple(normalized)

    if not isinstance(data.get("accepted"), bool):
        raise ValueError("accepted must be a boolean.")
    task_fingerprint = str(data.get("task_fingerprint") or "")
    guard_session_id = str(data.get("guard_session_id") or "")
    if not task_fingerprint or not guard_session_id:
        raise ValueError("Task status must identify its task and guard session.")
    exploratory_suppressed = data.get(
        "exploratory_tool_contact_suppressed", False
    )
    if not isinstance(exploratory_suppressed, bool):
        raise ValueError(
            "exploratory_tool_contact_suppressed must be a boolean."
        )
    return TaskJointStatus(
        accepted=bool(data["accepted"]),
        reason=str(data.get("reason") or ""),
        task_fingerprint=task_fingerprint,
        guard_session_id=guard_session_id,
        phase=str(data.get("phase") or ""),
        sequence=int(data.get("sequence", -1)),
        requested_positions=positions("requested_positions"),
        accepted_positions=positions("accepted_positions"),
        checked_samples=max(0, int(data.get("checked_samples", 0))),
        corridor_ok=bool(data.get("corridor_ok", False)),
        corridor_progress=optional_number("corridor_progress"),
        corridor_distance_m=optional_number("corridor_distance_m"),
        minimum_clearance_m=float(
            data.get("minimum_clearance_m", ROS2_RESEARCH_MINIMUM_CLEARANCE_M)
        ),
        minimum_self_distance_m=optional_number("minimum_self_distance_m"),
        minimum_world_distance_m=optional_number("minimum_world_distance_m"),
        first_body=str(data.get("first_body") or ""),
        second_body=str(data.get("second_body") or ""),
        world_object_count=max(0, int(data.get("world_object_count", 0))),
        world_objects=world_objects(),
        exploratory_tool_contact_suppressed=exploratory_suppressed,
        suppressed_tool_contact_sample_count=max(
            0, int(data.get("suppressed_tool_contact_sample_count", 0))
        ),
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
    global _native_joint_positions
    if len(values) != len(ROS2_JOINT_SI_ORDER):
        return
    _native_joint_positions = [float(value) for value in values]
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


def wait_for_collision_guard_world(
    minimum_object_count: int,
    *,
    timeout_sec: float = 8.0,
) -> Tuple[bool, str]:
    """Wait until the guard reports the synchronized MoveIt world snapshot."""

    expected = max(0, int(minimum_object_count))
    if expected == 0:
        return True, "No case collision objects were requested."
    deadline = time.monotonic() + float(timeout_sec)
    observed = 0
    while time.monotonic() < deadline:
        status = joint_command_status(max_age_sec=1.0)
        if status is not None:
            observed = max(observed, int(status.world_object_count))
            if status.world_object_count >= expected:
                return (
                    True,
                    f"Collision guard acknowledged {status.world_object_count} world object(s).",
                )
        try:
            import slicer

            slicer.app.processEvents()
        except Exception:
            pass
        time.sleep(0.02)
    return (
        False,
        f"Collision guard saw only {observed}/{expected} synchronized world object(s).",
    )


def last_accepted_joint_positions_si() -> dict[str, float]:
    """Return the latest accepted ordinary or phased simulation state."""

    joint_command_status()
    candidates = []
    if (
        _last_task_status is not None
        and len(_last_task_status.accepted_positions) == len(ROS2_JOINT_SI_ORDER)
    ):
        candidates.append(
            (_last_task_status_at, tuple(_last_task_status.accepted_positions))
        )
    if (
        _last_joint_status is not None
        and len(_last_joint_status.accepted_positions) == len(ROS2_JOINT_SI_ORDER)
    ):
        candidates.append(
            (_last_joint_status_at, tuple(_last_joint_status.accepted_positions))
        )
    if len(_native_joint_positions) == len(ROS2_JOINT_SI_ORDER):
        candidates.append((-1.0, tuple(float(value) for value in _native_joint_positions)))
    if not candidates:
        return {}
    _timestamp, values = max(candidates, key=lambda item: item[0])
    return dict(zip(ROS2_JOINT_SI_ORDER, values))


def monitored_joint_positions_si() -> dict[str, float]:
    """Return the joint vector currently reported on ROS ``/joint_states``.

    This is deliberately separate from the latest collision-guard acceptance
    and from the generic Motion Control widget's goal sliders. It is the state
    MoveIt's current-state monitor is expected to observe.
    """

    logic = get_motion_control_logic()
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if logic is None or robot_node is None:
        return {}
    try:
        values = logic.GetCurrentJointState(list(ROS2_JOINT_SI_ORDER))
    except Exception:
        return {}
    if values is None or len(values) != len(ROS2_JOINT_SI_ORDER):
        return {}
    try:
        result = {
            name: float(value)
            for name, value in zip(ROS2_JOINT_SI_ORDER, values)
        }
    except (TypeError, ValueError):
        return {}
    return result if all(isfinite(value) for value in result.values()) else {}


def _joint_state_error(
    expected: Mapping[str, float],
    observed: Mapping[str, float],
) -> tuple[float, tuple[str, ...]]:
    maximum_error = 0.0
    mismatched: list[str] = []
    for name in ROS2_JOINT_SI_ORDER:
        if name not in expected or name not in observed:
            mismatched.append(name)
            continue
        delta = float(observed[name]) - float(expected[name])
        if name in ROS2_CONTINUOUS_REVOLUTE_JOINTS:
            delta = (delta + pi) % (2.0 * pi) - pi
        error = abs(delta)
        maximum_error = max(maximum_error, error)
        tolerance = (
            ROS2_MONITORED_PRISMATIC_TOLERANCE_M
            if "Slider" in name
            else ROS2_MONITORED_REVOLUTE_TOLERANCE_RAD
        )
        if error > tolerance:
            mismatched.append(name)
    return maximum_error, tuple(mismatched)


def wait_for_monitored_joint_positions_si(
    expected_positions_si: Mapping[str, float],
    *,
    timeout_sec: float = ROS2_MONITORED_STATE_TIMEOUT_SEC,
) -> tuple[bool, str, dict[str, float], float]:
    """Wait until ROS and MoveIt's monitored current state equals *expected*.

    The bounded wait proves state handoff only; it never sends a command.
    """

    try:
        expected = dict(
            zip(ROS2_JOINT_SI_ORDER, joint_si_vector(expected_positions_si))
        )
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"Expected joint state is invalid: {exc}", {}, float("inf")
    deadline = time.monotonic() + max(0.0, float(timeout_sec))
    observed: dict[str, float] = {}
    maximum_error = float("inf")
    mismatched: tuple[str, ...] = ROS2_JOINT_SI_ORDER
    while time.monotonic() <= deadline:
        observed = monitored_joint_positions_si()
        if observed:
            maximum_error, mismatched = _joint_state_error(expected, observed)
            if not mismatched:
                return (
                    True,
                    "MoveIt monitored /joint_states matches the submitted Task Home.",
                    observed,
                    maximum_error,
                )
        try:
            import slicer

            slicer.app.processEvents()
        except Exception:
            pass
        ros_logic = get_ros2_logic()
        if ros_logic is not None:
            try:
                ros_logic.Spin()
            except Exception:
                pass
        time.sleep(0.02)
    if not observed:
        return (
            False,
            "No complete /joint_states vector reached Slicer before the bounded timeout.",
            {},
            maximum_error,
        )
    return (
        False,
        "MoveIt monitored state did not converge to Task Home; mismatched joints: "
        + ", ".join(mismatched),
        observed,
        maximum_error,
    )


def last_task_joint_status() -> Optional[TaskJointStatus]:
    """Return the latest transient phase-guard result for reporting."""

    return _last_task_status


def _on_task_status_modified(caller=None, event=None) -> None:
    del event
    global _last_task_status, _last_task_status_at
    try:
        payload = caller.GetLastMessage() if caller is not None else ""
        _last_task_status = parse_task_joint_status(str(payload or ""))
        _last_task_status_at = time.monotonic()
        if not _last_task_status.accepted:
            _restore_motion_control_positions(_last_task_status.accepted_positions)
    except (TypeError, ValueError, json.JSONDecodeError):
        return


def _ensure_task_status_subscriber():
    global _task_status_subscriber, _task_status_observer
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return None
    if _task_status_subscriber is not None:
        return _task_status_subscriber
    subscriber = ros_node.GetSubscriberNodeByTopic(ROS2_TASK_JOINT_STATUS_TOPIC)
    if subscriber is None:
        subscriber = ros_node.CreateAndAddSubscriberNode(
            "String", ROS2_TASK_JOINT_STATUS_TOPIC
        )
    if subscriber is None:
        return None
    subscriber.SetAttribute("DENTOBOT.TaskJointStatusSubscriber", "true")
    subscriber.SaveWithSceneOff()
    _task_status_subscriber = subscriber
    _task_status_observer = subscriber.AddObserver(
        "ModifiedEvent", _on_task_status_modified
    )
    return subscriber


def _ensure_task_publishers() -> tuple[object | None, object | None]:
    global _task_config_publisher, _task_command_publisher
    ros_node = ensure_default_ros2_node_in_scene()
    if ros_node is None:
        return None, None
    if _task_config_publisher is None:
        _task_config_publisher = ros_node.GetPublisherNodeByTopic(
            ROS2_TASK_GUARD_CONFIG_TOPIC
        ) or ros_node.CreateAndAddPublisherNode(
            "String", ROS2_TASK_GUARD_CONFIG_TOPIC
        )
    if _task_command_publisher is None:
        _task_command_publisher = ros_node.GetPublisherNodeByTopic(
            ROS2_TASK_JOINT_COMMAND_TOPIC
        ) or ros_node.CreateAndAddPublisherNode(
            "String", ROS2_TASK_JOINT_COMMAND_TOPIC
        )
    for publisher, role in (
        (_task_config_publisher, "DENTOBOT.TaskGuardConfigPublisher"),
        (_task_command_publisher, "DENTOBOT.TaskJointCommandPublisher"),
    ):
        if publisher is not None:
            publisher.SetAttribute(role, "true")
            publisher.SaveWithSceneOff()
    mark_slicer_ros2_runtime_nodes_transient()
    return _task_config_publisher, _task_command_publisher


def _wait_for_task_command_result(
    *,
    task_fingerprint: str,
    guard_session_id: str,
    phase: str,
    sequence: int,
    after_monotonic: float,
    timeout_sec: float,
) -> Optional[TaskJointStatus]:
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
        status = _last_task_status
        if (
            status is not None
            and _last_task_status_at > float(after_monotonic)
            and status.task_fingerprint == str(task_fingerprint)
            and status.guard_session_id == str(guard_session_id)
            and status.phase == str(phase)
            and status.sequence == int(sequence)
        ):
            return status
        time.sleep(0.01)
    return None


def world_ras_mm_to_base_m(point_ras_mm: Sequence[float], base_transform) -> list[float]:
    import numpy as np
    import vtk

    values = np.asarray(point_ras_mm, dtype=float)
    if values.shape != (3,) or not np.all(np.isfinite(values)):
        raise ValueError("World RAS point must contain three finite values.")
    base_to_world = vtk.vtkMatrix4x4()
    base_transform.GetMatrixTransformToWorld(base_to_world)
    world_to_base = vtk.vtkMatrix4x4()
    vtk.vtkMatrix4x4.Invert(base_to_world, world_to_base)
    source = [float(values[0]), float(values[1]), float(values[2]), 1.0]
    target = [0.0, 0.0, 0.0, 0.0]
    world_to_base.MultiplyPoint(source, target)
    return [float(target[index]) / 1000.0 for index in range(3)]


def configure_task_phase_guard(
    *,
    task_fingerprint: str,
    target_object_id: str,
    clearance_exempt_object_ids: Sequence[str],
    base_transform,
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    corridor_radius_mm: float,
    approach_standoff_mm: float,
) -> Tuple[bool, str]:
    global _last_task_config_json, _native_joint_positions
    config_publisher, command_publisher = _ensure_task_publishers()
    if (
        config_publisher is None
        or command_publisher is None
        or _ensure_task_status_subscriber() is None
    ):
        return False, "Could not create the transient task-guard ROS interface."
    payload = {
        "schema": ROS2_TASK_GUARD_CONFIG_SCHEMA,
        "mode": "simulation_only",
        "task_fingerprint": str(task_fingerprint),
        # A task may be re-planned without changing its immutable fingerprint.
        # This transient nonce identifies exactly one ordered preview session.
        # Re-publishing the same configuration is idempotent at the C++ guard,
        # while a new plan gets a clean sequence/corridor history.
        "guard_session_id": uuid4().hex,
        "target_object_id": str(target_object_id),
        "allowed_robot_link": "burr",
        # Approved task anatomy and guide objects omit only their burr-to-object
        # *distance* pairs in all phased states. Approach collision remains
        # strict. During terminal-contact/drilling preview, the C++ phase guard
        # suppresses only these configured burr pairs and reports every such
        # sample explicitly. Other robot links retain the 1 mm research margin
        # and strict collision checking.
        "clearance_exempt_object_ids": [
            str(value) for value in clearance_exempt_object_ids if str(value)
        ],
        "tool_tip_frame": ROS2_TOOL_TCP_LINK,
        "entry_base_m": world_ras_mm_to_base_m(entry_ras_mm, base_transform),
        "target_base_m": world_ras_mm_to_base_m(target_ras_mm, base_transform),
        "corridor_radius_m": float(corridor_radius_mm) / 1000.0,
        "approach_standoff_m": float(approach_standoff_mm) / 1000.0,
    }
    if not payload["task_fingerprint"] or not payload["target_object_id"]:
        return False, "Task-guard configuration is missing its task or target identity."
    _last_task_config_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if len(_native_joint_positions) != len(ROS2_JOINT_SI_ORDER):
        _last_task_config_json = ""
        return False, "The current six-joint state is unavailable for task-guard initialization."
    # Configuration and command use separate ROS topics, so DDS does not
    # guarantee cross-topic arrival order.  Sequence zero is a strict no-op
    # handshake at the already accepted state.  Only after the guard accepts
    # it may the façade begin Goal 1 at sequence one.
    handshake = {
        "schema": ROS2_TASK_JOINT_COMMAND_SCHEMA,
        "mode": "simulation_only",
        "task_fingerprint": str(task_fingerprint),
        "guard_session_id": payload["guard_session_id"],
        "phase": "approach",
        "sequence": 0,
        "joint_positions": [float(value) for value in _native_joint_positions],
    }
    handshake_json = json.dumps(handshake, sort_keys=True, separators=(",", ":"))
    status_after = _last_task_status_at
    deadline = time.monotonic() + ROS2_TASK_GUARD_SCENE_SYNC_TIMEOUT_SEC
    while time.monotonic() < deadline:
        config_publisher.Publish(_last_task_config_json)
        try:
            import slicer

            slicer.app.processEvents()
        except Exception:
            pass
        time.sleep(0.05)
        command_publisher.Publish(handshake_json)
        status = _wait_for_task_command_result(
            task_fingerprint=str(task_fingerprint),
            guard_session_id=payload["guard_session_id"],
            phase="approach",
            sequence=0,
            after_monotonic=status_after,
            timeout_sec=0.4,
        )
        if status is None:
            continue
        status_after = _last_task_status_at
        if status.accepted:
            _native_joint_positions = list(status.accepted_positions)
            return (
                True,
                "Task guard acknowledged the immutable configuration and strict current state.",
            )
        if (
            "No valid simulation task-guard configuration" in status.reason
            or "guard session does not match" in status.reason
            or "configured task-proximity collision object is missing"
            in status.reason
            or "selected target-tooth collision object is missing"
            in status.reason
        ):
            continue
        pair = (
            f" ({status.first_body or '?'} ↔ {status.second_body or '?'})"
            if status.first_body or status.second_body
            else ""
        )
        _last_task_config_json = ""
        return (
            False,
            "Task-guard initialization rejected the current state: "
            + status.reason
            + pair,
        )
    _last_task_config_json = ""
    return (
        False,
        "Task guard did not acknowledge the immutable configuration with its "
        "complete planning-scene object set.",
    )


def apply_task_phase_joint_positions(
    positions_si: Mapping[str, float],
    *,
    task_fingerprint: str,
    phase: str,
    sequence: int,
    timeout_sec: float = 6.0,
) -> Tuple[bool, str]:
    global _native_joint_positions
    config_publisher, command_publisher = _ensure_task_publishers()
    if (
        config_publisher is None
        or command_publisher is None
        or _ensure_task_status_subscriber() is None
    ):
        return False, "The transient task-guard ROS interface is unavailable."
    values = joint_si_vector(positions_si)
    prior = list(_native_joint_positions)
    status_before = _last_task_status_at
    command = {
        "schema": ROS2_TASK_JOINT_COMMAND_SCHEMA,
        "mode": "simulation_only",
        "task_fingerprint": str(task_fingerprint),
    }
    if not _last_task_config_json:
        return False, "No simulation task-guard configuration is active. Re-plan Goal 1."
    try:
        active_config = json.loads(_last_task_config_json)
        active_fingerprint = str(active_config.get("task_fingerprint") or "")
        active_session_id = str(active_config.get("guard_session_id") or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        active_fingerprint = ""
        active_session_id = ""
    if active_fingerprint != str(task_fingerprint):
        return (
            False,
            "The active simulation task guard belongs to another task. Re-plan Goal 1.",
        )
    if not active_session_id:
        return False, "The active simulation task-guard session is invalid. Re-plan Goal 1."
    command.update(
        {
            "guard_session_id": active_session_id,
            "phase": str(phase),
            "sequence": int(sequence),
            "joint_positions": values,
        }
    )
    command_publisher.Publish(json.dumps(command, sort_keys=True, separators=(",", ":")))
    status = _wait_for_task_command_result(
        task_fingerprint=str(task_fingerprint),
        guard_session_id=active_session_id,
        phase=str(phase),
        sequence=int(sequence),
        after_monotonic=status_before,
        timeout_sec=float(timeout_sec),
    )
    if status is None:
        return False, "Task guard did not answer the phased simulation command."
    if status.accepted:
        _native_joint_positions = values
        return True, status.reason
    _native_joint_positions = prior
    pair = (
        f" ({status.first_body or '?'} ↔ {status.second_body or '?'})"
        if status.first_body or status.second_body
        else ""
    )
    return (
        False,
        f"Task guard rejected {phase} sequence {int(sequence)}: "
        f"{status.reason}{pair}",
    )


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


def moveit_joint_goal_diagnostics(
    start_joint_positions_si: Mapping[str, float],
    goal_joint_positions_si: Mapping[str, float],
) -> dict[str, object]:
    """Canonicalize continuous goals and describe Task-Home continuity.

    Only joints declared continuous in the tracked URDF may cross a ``2*pi``
    representation boundary.  The other revolute joints have real bounded
    intervals even when an interval happens to span one full turn; silently
    wrapping those joints could request motion through a mechanical limit.
    """

    start_values = joint_si_vector(start_joint_positions_si)
    requested_goal_values = joint_si_vector(goal_joint_positions_si)
    start = dict(zip(ROS2_JOINT_SI_ORDER, start_values))
    requested_goal = dict(zip(ROS2_JOINT_SI_ORDER, requested_goal_values))
    submitted_goal = dict(requested_goal)
    adjustments: dict[str, float] = {}
    for name in ROS2_CONTINUOUS_REVOLUTE_JOINTS:
        requested = requested_goal[name]
        reference = start[name]
        turns = round((reference - requested) / (2.0 * pi))
        adjusted = requested + float(turns) * 2.0 * pi
        submitted_goal[name] = adjusted
        adjustment = adjusted - requested
        if abs(adjustment) > 1e-12:
            adjustments[name] = adjustment
    raw_deltas = {
        name: abs(requested_goal[name] - start[name])
        for name in ROS2_JOINT_SI_ORDER
    }
    effective_deltas = {
        name: abs(submitted_goal[name] - start[name])
        for name in ROS2_JOINT_SI_ORDER
    }
    raw_maximum_joint = max(raw_deltas, key=raw_deltas.get, default="")
    maximum_joint = max(effective_deltas, key=effective_deltas.get, default="")
    return {
        "start": start,
        "requested_goal": requested_goal,
        "submitted_goal": submitted_goal,
        "raw_deltas": raw_deltas,
        "effective_deltas": effective_deltas,
        "raw_maximum_joint": raw_maximum_joint,
        "raw_maximum_delta": (
            raw_deltas[raw_maximum_joint] if raw_maximum_joint else 0.0
        ),
        "maximum_joint": maximum_joint,
        "maximum_delta": effective_deltas[maximum_joint] if maximum_joint else 0.0,
        "continuous_adjustments": adjustments,
    }


def diagnose_moveit_joint_segment(
    start_joint_positions_si: Mapping[str, float],
    goal_joint_positions_si: Mapping[str, float],
    *,
    maximum_samples: int = 721,
) -> JointSegmentDiagnostic:
    """Probe the direct joint chord for the first exact MoveIt collision.

    This is diagnostic only.  A colliding direct chord does not prove that no
    curved free-space plan exists, and a clear chord is never promoted as a
    plan.  No joint state is published or applied.
    """

    _logic, robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False,
        require_goal=False,
    )
    if error or robot_node is None:
        return JointSegmentDiagnostic(
            sample_count=0,
            collision_found=False,
            message=error or "MoveIt robot context is unavailable.",
        )
    try:
        diagnostic = moveit_joint_goal_diagnostics(
            start_joint_positions_si,
            goal_joint_positions_si,
        )
        start = diagnostic["start"]
        goal = diagnostic["submitted_goal"]
        effective_deltas = diagnostic["effective_deltas"]
        requested_intervals = []
        for name in ROS2_JOINT_SI_ORDER:
            maximum_step = (
                ROS2_GUARD_MAX_PRISMATIC_STEP_M
                if "Slider" in name
                else ROS2_GUARD_MAX_REVOLUTE_STEP_RAD
            )
            requested_intervals.append(
                int(ceil(float(effective_deltas[name]) / maximum_step))
            )
        interval_count = max(1, min(max(requested_intervals), maximum_samples - 1))
        sample_count = interval_count + 1
        for sample_index in range(sample_count):
            fraction = float(sample_index) / float(interval_count)
            values = [
                float(start[name])
                + (float(goal[name]) - float(start[name])) * fraction
                for name in ROS2_JOINT_SI_ORDER
            ]
            encoded_pairs = robot_node.GetMoveItCollidingBodyPairs(
                ROS2_PLANNING_GROUP,
                values,
            )
            pairs = tuple(
                tuple(str(value).split("\t", 1))
                for value in encoded_pairs
                if "\t" in str(value)
            )
            if pairs:
                first_pair = " <-> ".join(pairs[0])
                return JointSegmentDiagnostic(
                    sample_count=sample_count,
                    collision_found=True,
                    first_collision_fraction=fraction,
                    first_collision_pairs=pairs,
                    message=(
                        "The direct Task-Home-to-goal joint interpolation first "
                        f"collides at {fraction * 100.0:.1f}%: {first_pair}. "
                        "This does not rule out a curved collision-free plan."
                    ),
                )
        return JointSegmentDiagnostic(
            sample_count=sample_count,
            collision_found=False,
            message=(
                f"No collision pair was found on the direct joint interpolation "
                f"at {sample_count} bounded sample(s). The chord is diagnostic "
                "only and was not promoted as a plan."
            ),
        )
    except Exception as exc:
        return JointSegmentDiagnostic(
            sample_count=0,
            collision_found=False,
            message=f"Direct joint-interpolation diagnosis failed: {exc}",
        )


def show_moveit_joint_goal(
    joint_positions_si: Mapping[str, float],
) -> tuple[bool, str]:
    """Display one already-selected joint goal on the transient goal robot."""

    logic, robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False,
        require_goal=False,
    )
    if error or logic is None or robot_node is None:
        return False, error or "MoveIt goal-robot context is unavailable."
    try:
        values = joint_si_vector(joint_positions_si)
        logic.last_ik_solution = list(values)
        logic.updategoalTransformsFromJointsKDL(robot_node, values)
    except Exception as exc:
        return False, f"Could not display the selected MoveIt goal state: {exc}"
    return True, "Displayed the selected MoveIt plan endpoint."


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
                "IK solution found for dentobot_drill_tip_provisional. Press Plan to compute "
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
        "MoveIt ready · group dentobot_arm · TCP dentobot_drill_tip_provisional · plan/preview "
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
    # DENTOWorkflow is the sole command-state authority. The optional generic
    # Motion Control widget may display diagnostics, but opening it must never
    # replace the native vector with slider or delayed /joint_states values.
    if len(_native_joint_positions) == len(ROS2_JOINT_SI_ORDER):
        return list(_native_joint_positions)
    try:
        import slicer

        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
        values = (
            getattr(widget, "jointPositionsRad", None)
            if widget is not None and getattr(widget, "_dentobotUiConfigured", False)
            else None
        )
        if values and len(values) == len(ROS2_JOINT_SI_ORDER):
            return [float(value) for value in values]
    except Exception:
        pass
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
    global _native_joint_positions
    if find_ros2_robot_by_name(ROS2_ROBOT_NAME) is None:
        return False, "The DENTOBOT ROS robot is not connected."
    try:
        values = joint_si_vector(positions_si)
    except (KeyError, TypeError, ValueError) as exc:
        return False, str(exc)
    prior_native = list(_native_joint_positions)
    _native_joint_positions = list(values)
    stream_was_active = bool(
        _slicer_joint_command_timer is not None
        and _slicer_joint_command_timer.isActive()
    )
    if stream_was_active:
        _slicer_joint_command_timer.stop()
    status_before = _last_joint_status_at
    try:
        if not _publish_slicer_joint_command():
            _native_joint_positions = prior_native
            return False, "Failed to publish the simulated joint vector."
        result = _wait_for_joint_command_result(
            values,
            after_monotonic=status_before,
        )
        if result is None:
            _native_joint_positions = prior_native
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


def show_goal_robot_joint_positions(
    positions_si: Mapping[str, float],
) -> Tuple[bool, str]:
    """Apply a display-only diagnostic state to the translucent goal robot."""
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    motion_logic = get_motion_control_logic()
    if robot_node is None or motion_logic is None:
        return False, "Connect the simulation-only ROS robot first."
    if robot_node.GetNumberOfNodeReferences("goal_model") == 0:
        return False, "The transient goal robot is unavailable."
    try:
        values = joint_si_vector(positions_si)
        motion_logic.updategoalTransformsFromJointsKDL(robot_node, values)
        for index in range(robot_node.GetNumberOfNodeReferences("goal_model")):
            model = robot_node.GetNthNodeReference("goal_model", index)
            if model is not None and model.GetDisplayNode() is not None:
                model.GetDisplayNode().SetVisibility(True)
                model.GetDisplayNode().SetOpacity(0.35)
        return True, "Showing the selected last-valid state on the display-only goal robot."
    except Exception as exc:
        return False, f"Could not show the diagnostic goal state: {exc}"


def clear_phase_plan_tcp_path() -> None:
    """Remove the transient TCP path used by the Step 6 phase preview.

    The path is display-only evidence.  It is deliberately a transient MRML
    model and is never serialized into a case package or published to
    MoveIt's PlanningScene.
    """

    try:
        import slicer
    except ImportError:
        return
    for node in list(slicer.util.getNodesByClass("vtkMRMLModelNode")):
        if node.GetAttribute(ROS2_PHASE_PATH_ATTRIBUTE) == "true":
            slicer.mrmlScene.RemoveNode(node)


def show_phase_plan_tcp_path(
    waypoint_joint_vectors_si: Sequence[Mapping[str, float]],
    base_transform,
    *,
    phase: str = "approach",
) -> Tuple[bool, str]:
    """Render a transient world-RAS TCP polyline for a planned phase.

    Each point is obtained from the same SlicerROS2 KDL chain that drives the
    robot model, then transformed by the locked base into world RAS mm.  This
    avoids inventing a second coordinate conversion and makes the line an
    honest view of the actual joint waypoints that will be previewed.  It has
    no collision/planning authority and is excluded from all outgoing obstacle
    payloads.
    """

    try:
        import slicer
        import vtk
    except ImportError:
        return False, ROS2_UNAVAILABLE_MESSAGE
    clear_phase_plan_tcp_path()
    waypoints = tuple(waypoint_joint_vectors_si or ())
    if len(waypoints) < 2:
        return False, "A phase path needs at least two joint waypoints."
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if robot_node is None:
        return False, "The transient ROS robot is unavailable for TCP path display."
    if base_transform is None:
        return False, "The locked robot base is unavailable for TCP path display."
    base_world = vtk.vtkMatrix4x4()
    if base_transform.GetMatrixTransformToWorld(base_world) is False:
        return False, "Could not resolve the robot base in world RAS."
    points = vtk.vtkPoints()
    for waypoint in waypoints:
        try:
            pose_base = vtk.vtkMatrix4x4()
            pose_base.Identity()
            if (
                robot_node.ComputeKDLFK(
                    joint_si_vector(waypoint),
                    pose_base,
                    ROS2_TOOL_TCP_LINK,
                )
                is None
            ):
                clear_phase_plan_tcp_path()
                return False, f"Could not compute {ROS2_TOOL_TCP_LINK} FK for the planned path."
            pose_world = vtk.vtkMatrix4x4()
            vtk.vtkMatrix4x4.Multiply4x4(base_world, pose_base, pose_world)
            points.InsertNextPoint(
                float(pose_world.GetElement(0, 3)),
                float(pose_world.GetElement(1, 3)),
                float(pose_world.GetElement(2, 3)),
            )
        except (KeyError, TypeError, ValueError, RuntimeError) as exc:
            clear_phase_plan_tcp_path()
            return False, f"Could not compute the planned TCP path: {exc}"
    polyline = vtk.vtkPolyLine()
    polyline.GetPointIds().SetNumberOfIds(points.GetNumberOfPoints())
    for index in range(points.GetNumberOfPoints()):
        polyline.GetPointIds().SetId(index, index)
    cells = vtk.vtkCellArray()
    cells.InsertNextCell(polyline)
    polydata = vtk.vtkPolyData()
    polydata.SetPoints(points)
    polydata.SetLines(cells)
    node = slicer.mrmlScene.AddNewNodeByClass(
        "vtkMRMLModelNode",
        f"[Step 6] Planned TCP Path ({str(phase).title()})",
    )
    node.SetAttribute(ROS2_PHASE_PATH_ATTRIBUTE, "true")
    node.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyPhasePlan")
    node.SetAttribute("DENTOBOT.Phase", str(phase))
    node.SetAttribute("DENTOBOT.CoordinateFrame", ROS2_FIXED_FRAME)
    node.SaveWithSceneOff()
    node.SetAndObservePolyData(polydata)
    node.CreateDefaultDisplayNodes()
    display = node.GetDisplayNode()
    if display is not None:
        display.SetVisibility(True)
        display.SetColor(1.0, 0.65, 0.05)
        display.SetOpacity(0.95)
        set_line_width = getattr(display, "SetLineWidth", None)
        if set_line_width is not None:
            set_line_width(4.0)
    return True, (
        f"Showing the {str(phase)} TCP phase path ({points.GetNumberOfPoints()} points) "
        "in world RAS."
    )


def show_motion_diagnostic_evidence(
    *,
    first_invalid_ras_mm: Optional[Sequence[float]],
    collision_pairs: Sequence[Sequence[str]],
) -> Tuple[bool, str]:
    """Show a transient first-invalid marker and collision-object highlight."""
    try:
        import slicer
        import vtk

        for node in list(slicer.util.getNodesByClass("vtkMRMLMarkupsFiducialNode")):
            if node.GetAttribute("DENTOBOT.MotionDiagnosticBoundary") == "true":
                slicer.mrmlScene.RemoveNode(node)
        if first_invalid_ras_mm is not None:
            point = tuple(float(value) for value in first_invalid_ras_mm)
            if len(point) != 3 or not all(isfinite(value) for value in point):
                raise ValueError("First-invalid point must be finite world RAS mm.")
            marker = slicer.mrmlScene.AddNewNodeByClass(
                "vtkMRMLMarkupsFiducialNode",
                "[Step 6 Diagnostic] First Invalid Requested Point",
            )
            marker.SetAttribute("DENTOBOT.MotionDiagnosticBoundary", "true")
            marker.SetAttribute("DENTOBOT.IntendedUse", "DisplayOnlyDiagnostic")
            marker.SaveWithSceneOff()
            marker.AddControlPointWorld(vtk.vtkVector3d(*point), "First invalid")
            marker.SetLocked(True)
            marker.CreateDefaultDisplayNodes()
            marker.GetDisplayNode().SetSelectedColor(1.0, 0.15, 0.10)
            marker.GetDisplayNode().SetColor(1.0, 0.15, 0.10)
            marker.GetDisplayNode().SetGlyphScale(3.0)
        collision_ids = {
            str(body)
            for pair in collision_pairs
            for body in pair
            if str(body) and not str(body).startswith("__")
        }
        highlighted = []
        for node in slicer.util.getNodesByClass("vtkMRMLModelNode"):
            if node.GetAttribute("DENTOBOT.CollisionAuditCopy") != "true":
                continue
            display = node.GetDisplayNode()
            object_id = str(
                node.GetAttribute("DENTOBOT.OutgoingCollisionObjectId") or ""
            )
            if display:
                if object_id in collision_ids:
                    display.SetColor(1.0, 0.15, 0.10)
                    display.SetVisibility(True)
                    highlighted.append(object_id)
                else:
                    display.SetColor(0.10, 0.95, 0.95)
        return True, (
            "Displayed the retained first-invalid point"
            + (
                " and highlighted collision object(s): " + ", ".join(highlighted)
                if highlighted
                else "; no named world collision object was reported"
            )
            + "."
        )
    except Exception as exc:
        return False, f"Could not show diagnostic boundary evidence: {exc}"


def connect_dentobot_motion_control(
    base_transform,
    hide_mrml_robot: bool = True,
    mrml_robot_models: Optional[list] = None,
    open_motion_module: bool = True,
    start_stack_if_needed: bool = True,
    initial_joint_positions_si: Optional[Mapping[str, float]] = None,
) -> Tuple[Optional[object], str]:
    """Create the Slicer robot and seed plan-only control from reviewed state."""
    global _native_joint_positions
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

    if initial_joint_positions_si is not None:
        try:
            _native_joint_positions = joint_si_vector(initial_joint_positions_si)
        except (KeyError, TypeError, ValueError) as exc:
            return None, f"The reviewed Task Home joint vector is invalid: {exc}"

    streamed, stream_error = start_slicer_joint_command_stream()
    if not streamed:
        return None, stream_error
    base_transform.SetAttribute(ROS2_MOTION_ACTIVE_ATTRIBUTE, "true")
    if hide_mrml_robot and mrml_robot_models:
        set_mrml_link_models_visible(mrml_robot_models, False)
    if open_motion_module:
        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
        if widget is not None:
            widget.setParameterNode(parameter_node)
            if not configure_dentobot_motion_control_ui(widget, parameter_node):
                return None, "Could not configure the DENTOBOT plan-only Motion Control UI."
        try:
            if slicer.util.mainWindow() is not None:
                slicer.util.selectModule(ROS2_MOTION_MODULE_NAME)
        except RuntimeError:
            pass
    return robot_node, ""


def prepare_dentobot_motion_diagnostics() -> Tuple[bool, str]:
    """Configure the optional generic widget only for explicit expert use."""

    try:
        import slicer

        widget = slicer.util.getModuleWidget(ROS2_MOTION_MODULE_NAME)
    except Exception as exc:
        return False, f"ROS2MotionControl diagnostics are unavailable ({exc})."
    logic = get_motion_control_logic()
    robot = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    if widget is None or logic is None or robot is None:
        return False, "Connect the DENTOBOT runtime before opening expert diagnostics."
    parameter_node = logic.getParameterNode()
    widget.setParameterNode(parameter_node)
    if not configure_dentobot_motion_control_ui(widget, parameter_node):
        return False, "Could not configure plan-only expert diagnostics."
    return True, "Expert ROS diagnostics configured; execution remains disabled."


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


def _matrix4_rows(matrix) -> tuple[tuple[float, ...], ...]:
    """Return one finite homogeneous matrix without importing VTK."""

    try:
        if hasattr(matrix, "GetElement"):
            rows = tuple(
                tuple(float(matrix.GetElement(row, column)) for column in range(4))
                for row in range(4)
            )
        else:
            rows = tuple(
                tuple(float(matrix[row][column]) for column in range(4))
                for row in range(4)
            )
    except (IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"Pose matrix must contain 16 finite values: {exc}") from exc
    if len(rows) != 4 or any(len(row) != 4 for row in rows):
        raise ValueError("Pose matrix must be 4 by 4.")
    if not all(isfinite(value) for row in rows for value in row):
        raise ValueError("Pose matrix must contain only finite values.")
    return rows


def _validate_rigid_pose_rows(
    rows: Sequence[Sequence[float]],
    *,
    label: str,
    tolerance: float = 1e-4,
) -> None:
    """Fail closed on scale, shear, reflection, or a non-homogeneous pose."""

    matrix = _matrix4_rows(rows)
    if any(abs(matrix[3][index]) > tolerance for index in range(3)) or abs(
        matrix[3][3] - 1.0
    ) > tolerance:
        raise ValueError(f"{label} is not a homogeneous rigid transform.")
    columns = tuple(
        tuple(matrix[row][column] for row in range(3)) for column in range(3)
    )
    for index, column in enumerate(columns):
        norm = sqrt(sum(value * value for value in column))
        if abs(norm - 1.0) > tolerance:
            raise ValueError(f"{label} rotation column {index} is not unit length.")
    for first in range(3):
        for second in range(first + 1, 3):
            dot = sum(
                columns[first][index] * columns[second][index]
                for index in range(3)
            )
            if abs(dot) > tolerance:
                raise ValueError(f"{label} rotation contains scale or shear.")
    determinant = (
        matrix[0][0]
        * (matrix[1][1] * matrix[2][2] - matrix[1][2] * matrix[2][1])
        - matrix[0][1]
        * (matrix[1][0] * matrix[2][2] - matrix[1][2] * matrix[2][0])
        + matrix[0][2]
        * (matrix[1][0] * matrix[2][1] - matrix[1][1] * matrix[2][0])
    )
    if determinant <= 0.0 or abs(determinant - 1.0) > 5.0 * tolerance:
        raise ValueError(f"{label} rotation must be right-handed and orthonormal.")


def _rigid_pose_world_to_reference_rows(
    pose_world,
    reference_to_world,
) -> tuple[tuple[float, ...], ...]:
    """Express a rigid world pose in a rigid reference frame, preserving mm."""

    world = _matrix4_rows(pose_world)
    reference = _matrix4_rows(reference_to_world)
    _validate_rigid_pose_rows(world, label="Cartesian world pose")
    _validate_rigid_pose_rows(reference, label="Robot base pose")
    reference_rotation = tuple(
        tuple(reference[row][column] for column in range(3)) for row in range(3)
    )
    world_rotation = tuple(
        tuple(world[row][column] for column in range(3)) for row in range(3)
    )
    relative_rotation = tuple(
        tuple(
            sum(
                reference_rotation[index][row] * world_rotation[index][column]
                for index in range(3)
            )
            for column in range(3)
        )
        for row in range(3)
    )
    world_offset = tuple(world[row][3] - reference[row][3] for row in range(3))
    relative_translation = tuple(
        sum(reference_rotation[index][row] * world_offset[index] for index in range(3))
        for row in range(3)
    )
    return tuple(
        tuple(relative_rotation[row][column] for column in range(3))
        + (relative_translation[row],)
        for row in range(3)
    ) + ((0.0, 0.0, 0.0, 1.0),)


def _pose_residual_mm_degrees(
    actual,
    expected,
) -> tuple[float, float]:
    """Return translation and shortest rotation residual between rigid poses."""

    actual_rows = _matrix4_rows(actual)
    expected_rows = _matrix4_rows(expected)
    _validate_rigid_pose_rows(actual_rows, label="Actual TCP pose")
    _validate_rigid_pose_rows(expected_rows, label="Requested TCP pose")
    position_error = sqrt(
        sum(
            (actual_rows[row][3] - expected_rows[row][3]) ** 2
            for row in range(3)
        )
    )
    # Normalize corresponding rotation columns before taking trace(Ra^T Re).
    # MRML matrices may contain harmless floating-point drift from a chain of
    # rigid transforms; without this normalization even comparing a matrix to
    # itself can report a small, fictitious angular error.
    relative_trace = 0.0
    for column in range(3):
        actual_column = tuple(actual_rows[row][column] for row in range(3))
        expected_column = tuple(expected_rows[row][column] for row in range(3))
        actual_norm = sqrt(sum(value * value for value in actual_column))
        expected_norm = sqrt(sum(value * value for value in expected_column))
        relative_trace += sum(
            actual_column[row] * expected_column[row] for row in range(3)
        ) / (actual_norm * expected_norm)
    cosine = max(-1.0, min(1.0, 0.5 * (relative_trace - 1.0)))
    return float(position_error), float(degrees(acos(cosine)))


def _pose_matrices_world_to_base_mm(pose_matrices, base_transform):
    """Convert explicit world-RAS/mm poses once into base-link/mm poses."""

    if base_transform is None:
        raise ValueError("Cartesian planning requires the locked robot-base transform.")
    import vtk

    base_to_world = vtk.vtkMatrix4x4()
    result = base_transform.GetMatrixTransformToWorld(base_to_world)
    if result is False:
        raise ValueError("Could not resolve the robot-base transform in world RAS.")
    base_rows = _matrix4_rows(base_to_world)
    converted = []
    for pose_world in pose_matrices:
        rows = _rigid_pose_world_to_reference_rows(pose_world, base_rows)
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(4):
            for column in range(4):
                matrix.SetElement(row, column, rows[row][column])
        converted.append(matrix)
    return converted


def _cartesian_start_continuity(
    robot_node,
    start_joint_positions_si: Mapping[str, float],
    first_pose_base_mm,
) -> tuple[float, float]:
    """Compare the explicit MoveIt start-state FK with waypoint zero."""

    import vtk

    actual_pose = vtk.vtkMatrix4x4()
    actual_pose.Identity()
    fk_result = robot_node.ComputeKDLFK(
        joint_si_vector(start_joint_positions_si),
        actual_pose,
        ROS2_TOOL_TCP_LINK,
    )
    if fk_result is None:
        raise ValueError(
            f"Could not compute {ROS2_TOOL_TCP_LINK} FK for the Cartesian start state."
        )
    return _pose_residual_mm_degrees(actual_pose, first_pose_base_mm)


def tool_pose_matrices_world_mm(
    entry_ras_mm: Sequence[float],
    target_ras_mm: Sequence[float],
    sample_count: int,
    *,
    axial_roll_start_deg: float = 0.0,
    axial_roll_end_deg: float = 0.0,
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

    roll_start = float(axial_roll_start_deg)
    roll_end = float(axial_roll_end_deg)
    if not isfinite(roll_start) or not isfinite(roll_end):
        raise ValueError("Tool-axis roll must be finite.")
    points = np.linspace(entry, target, max(2, int(sample_count)))
    rolls = np.linspace(roll_start, roll_end, len(points))
    matrices = []
    for point, roll_deg in zip(points, rolls):
        angle = radians(float(roll_deg))
        rolled_x = cos(angle) * x_axis + sin(angle) * y_axis
        rolled_y = -sin(angle) * x_axis + cos(angle) * y_axis
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        for row in range(3):
            matrix.SetElement(row, 0, float(rolled_x[row]))
            matrix.SetElement(row, 1, float(rolled_y[row]))
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
    start_joint_positions_si: Optional[Mapping[str, float]] = None,
    axial_roll_start_deg: float = 0.0,
    axial_roll_end_deg: float = 0.0,
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
        world_poses = tool_pose_matrices_world_mm(
            entry_ras_mm,
            target_ras_mm,
            sample_count,
            axial_roll_start_deg=axial_roll_start_deg,
            axial_roll_end_deg=axial_roll_end_deg,
        )
        poses = _pose_matrices_world_to_base_mm(world_poses, base_transform)
        start_names = None
        start_values = None
        start_position_error_mm = None
        start_orientation_error_deg = None
        if start_joint_positions_si is not None:
            start_names = list(ROS2_JOINT_SI_ORDER)
            start_values = joint_si_vector(start_joint_positions_si)
            (
                start_position_error_mm,
                start_orientation_error_deg,
            ) = _cartesian_start_continuity(
                robot_node,
                start_joint_positions_si,
                poses[0],
            )
            if (
                start_position_error_mm > CARTESIAN_START_POSITION_TOLERANCE_MM
                or start_orientation_error_deg
                > CARTESIAN_START_ORIENTATION_TOLERANCE_DEG
            ):
                return MoveItCartesianResult(
                    False,
                    "Refusing an unintended Cartesian bridge: the explicit "
                    f"start-state TCP differs from waypoint zero by "
                    f"{start_position_error_mm:.3f} mm and "
                    f"{start_orientation_error_deg:.3f} deg in {ROS2_FIXED_FRAME}.",
                    coordinate_frame=ROS2_FIXED_FRAME,
                    start_position_error_mm=start_position_error_mm,
                    start_orientation_error_deg=start_orientation_error_deg,
                )
        # A coarse Cartesian step can stop at a local IK-continuation failure
        # even when closer seeded waypoints remain solvable. Retry only with
        # bounded, progressively finer steps and keep the best result. The
        # requested poses/orientation and exact Entry-to-Target line do not
        # change. Collision-aware requests retain one 1 mm attempt; exploratory
        # contact/drilling requests may use all three resolutions.
        eef_steps = (
            (ROS2_CARTESIAN_EEF_STEP_ATTEMPTS_M[0],)
            if avoid_collisions
            else ROS2_CARTESIAN_EEF_STEP_ATTEMPTS_M
        )
        trajectory = None
        fraction = 0.0
        used_eef_step_m = float(eef_steps[0])
        for eef_step_m in eef_steps:
            candidate = motion_logic.PlanMoveItCartesianTrajectoryFromPoseMarkers(
                motionControlNode=motion_node,
                groupName=ROS2_PLANNING_GROUP,
                poseMarkers=poses,
                # These raw matrices are explicitly base-local. The generic
                # SlicerROS2 helper must not reinterpret their coordinates.
                relativeToNode=None,
                robotNode=robot_node,
                eefStepMeters=float(eef_step_m),
                jumpThreshold=0.0,
                avoidCollisions=bool(avoid_collisions),
                velocityScaling=0.2,
                accelerationScaling=0.2,
                planningTimeSec=10.0,
                startJointNames=start_names,
                startJointValues=start_values,
                linkName=ROS2_TOOL_TCP_LINK,
            )
            candidate_fraction = float(motion_node.GetLastCartesianPathFraction())
            if candidate is not None and (
                trajectory is None or candidate_fraction >= fraction
            ):
                trajectory = candidate
                fraction = candidate_fraction
                used_eef_step_m = float(eef_step_m)
            if (
                avoid_collisions
                and candidate is not None
                and candidate_fraction >= float(minimum_fraction)
            ):
                break
    except Exception as exc:
        return MoveItCartesianResult(False, f"MoveIt Cartesian request failed: {exc}")
    requested_entry = tuple(float(value) for value in entry_ras_mm)
    requested_target = tuple(float(value) for value in target_ras_mm)
    requested_length_mm = sqrt(
        sum((target - entry) ** 2 for entry, target in zip(requested_entry, requested_target))
    )
    if trajectory is None:
        return MoveItCartesianResult(
            False,
            f"MoveIt returned no Cartesian trajectory (fraction {fraction:.3f}).",
            fraction=fraction,
            coordinate_frame=ROS2_FIXED_FRAME,
            start_position_error_mm=start_position_error_mm,
            start_orientation_error_deg=start_orientation_error_deg,
            axial_roll_deg=float(axial_roll_end_deg),
            eef_step_m=used_eef_step_m,
            requested_path_length_mm=requested_length_mm,
            completed_distance_mm=requested_length_mm * max(0.0, min(1.0, fraction)),
            failure_classification="no_cartesian_trajectory",
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
    bounded_fraction = max(0.0, min(1.0, fraction))
    first_invalid_index = -1
    first_invalid_ras = None
    if fraction < float(minimum_fraction):
        requested_pose_count = max(2, len(world_poses))
        first_invalid_index = min(
            requested_pose_count - 1,
            max(1, int(floor(bounded_fraction * (requested_pose_count - 1))) + 1),
        )
        first_invalid_pose = world_poses[first_invalid_index]
        first_invalid_ras = tuple(
            float(first_invalid_pose.GetElement(axis, 3)) for axis in range(3)
        )
        seed_values = [float(waypoints[-1][name]) for name in ROS2_JOINT_SI_ORDER]
        collision_solution = list(
            robot_node.ComputeMoveItIK(
                poses[first_invalid_index],
                ROS2_TOOL_TCP_LINK,
                seed_values,
                0.2,
                True,
            )
        )
        kinematics_solution = list(
            robot_node.ComputeMoveItIK(
                poses[first_invalid_index],
                ROS2_TOOL_TCP_LINK,
                seed_values,
                0.2,
                False,
            )
        )
        if kinematics_solution and not collision_solution:
            classification = "collision_induced_ik_failure"
        elif not kinematics_solution:
            classification = "kinematic_joint_or_singularity_failure"
        else:
            classification = "cartesian_continuity_or_interpolation_failure"
        first_invalid_joint_positions = (
            {
                name: float(value)
                for name, value in zip(ROS2_JOINT_SI_ORDER, kinematics_solution)
            }
            if len(kinematics_solution) == len(ROS2_JOINT_SI_ORDER)
            else None
        )
        collision_pairs = ()
        if first_invalid_joint_positions is not None:
            encoded_pairs = robot_node.GetMoveItCollidingBodyPairs(
                ROS2_PLANNING_GROUP,
                [
                    first_invalid_joint_positions[name]
                    for name in ROS2_JOINT_SI_ORDER
                ],
            )
            collision_pairs = tuple(
                tuple(str(value).split("\t", 1))
                for value in encoded_pairs
                if "\t" in str(value)
            )
        return MoveItCartesianResult(
            False,
            f"MoveIt planned only {fraction * 100.0:.1f}% of the requested path "
            f"after bounded Cartesian steps down to "
            f"{min(eef_steps) * 1000.0:.2f} mm; {len(waypoints)} partial "
            "joint waypoint(s) were retained for diagnosis.",
            fraction=fraction,
            waypoint_joint_vectors_si=tuple(waypoints),
            waypoint_times_sec=tuple(times),
            coordinate_frame=ROS2_FIXED_FRAME,
            start_position_error_mm=start_position_error_mm,
            start_orientation_error_deg=start_orientation_error_deg,
            axial_roll_deg=float(axial_roll_end_deg),
            eef_step_m=used_eef_step_m,
            requested_path_length_mm=requested_length_mm,
            completed_distance_mm=requested_length_mm * bounded_fraction,
            last_valid_waypoint_index=len(waypoints) - 1,
            first_invalid_requested_index=first_invalid_index,
            last_valid_joint_positions_si=dict(waypoints[-1]),
            first_invalid_ras_mm=first_invalid_ras,
            failure_classification=classification,
            collision_aware_ik_at_first_invalid=bool(collision_solution),
            kinematics_only_ik_at_first_invalid=bool(kinematics_solution),
            first_invalid_joint_positions_si=first_invalid_joint_positions,
            first_invalid_collision_pairs=collision_pairs,
        )
    return MoveItCartesianResult(
        True,
        f"MoveIt planned {len(waypoints)} points with Cartesian fraction "
        f"{fraction:.3f} using a {used_eef_step_m * 1000.0:.2f} mm step.",
        fraction=fraction,
        waypoint_joint_vectors_si=tuple(waypoints),
        waypoint_times_sec=tuple(times),
        coordinate_frame=ROS2_FIXED_FRAME,
        start_position_error_mm=start_position_error_mm,
        start_orientation_error_deg=start_orientation_error_deg,
        axial_roll_deg=float(axial_roll_end_deg),
        eef_step_m=used_eef_step_m,
        requested_path_length_mm=requested_length_mm,
        completed_distance_mm=requested_length_mm,
        last_valid_waypoint_index=len(waypoints) - 1,
        last_valid_joint_positions_si=dict(waypoints[-1]),
    )


def _dentobot_native_motion_context(
    *,
    initialize_goal: bool = False,
    require_goal: bool = True,
):
    """Return native logic/MRML objects without entering the generic widget.

    A draggable TCP goal is presentation state, not a prerequisite for
    explicit joint-state planning, state-validity, or FK queries.  Callers
    performing those read-only/state-owned operations set ``require_goal`` to
    false; interactive IK callers retain the fail-closed goal requirement.
    """
    global _native_goal_transform
    try:
        import slicer
    except ImportError:
        return None, None, None, ROS2_UNAVAILABLE_MESSAGE
    robot_node = find_ros2_robot_by_name(ROS2_ROBOT_NAME)
    logic = get_motion_control_logic()
    if robot_node is None or logic is None:
        return None, None, None, "Connect DENTOBOT Motion Control first."
    if _native_goal_transform is not None and _native_goal_transform.GetScene() is None:
        _native_goal_transform = None
    if initialize_goal and _native_goal_transform is None:
        root_and_tip = robot_node.FindRootAndTipLinks()
        root_link = str(root_and_tip[0]) if root_and_tip else ROS2_FIXED_FRAME
        state = logic.EnterControlMode(
            robot_node,
            root_link,
            ROS2_TOOL_TCP_LINK,
            ROS2_TOOL_TCP_LINK,
            baseGoalColor=(0.25, 0.75, 0.95),
        )
        if not state:
            return logic, robot_node, None, "Could not create native TCP goal controls."
        _native_goal_transform = state.get("fromTransform")
        _mark_node_and_storage_transient(_native_goal_transform)
        try:
            _mark_node_and_storage_transient(slicer.util.getNode("ProbeSphere"))
        except Exception:
            pass
        mark_slicer_ros2_runtime_nodes_transient()
    if require_goal and _native_goal_transform is None:
        return logic, robot_node, None, "Create the DENTOBOT TCP goal control first."
    return logic, robot_node, _native_goal_transform, ""


def ensure_moveit_tcp_goal_control():
    """Create or reuse the draggable provisional-TCP goal transform."""
    logic, _robot, goal_node, error = _dentobot_native_motion_context(
        initialize_goal=True
    )
    if error or logic is None or goal_node is None:
        return False, error or "TCP goal control is unavailable.", None
    return (
        True,
        "DENTOBOT TCP goal is ready. Drag the probe, then solve IK.",
        goal_node,
    )


def set_moveit_tcp_goal_matrix(matrix_goal_parent):
    """Set the generic Motion Control TCP probe without exposing its widget."""
    ok, message, goal_node = ensure_moveit_tcp_goal_control()
    if not ok or goal_node is None:
        return False, message, None
    try:
        if hasattr(matrix_goal_parent, "GetElement"):
            goal_node.SetMatrixTransformToParent(matrix_goal_parent)
        else:
            import vtk

            matrix = vtk.vtkMatrix4x4()
            matrix.Identity()
            for row in range(4):
                for column in range(4):
                    matrix.SetElement(row, column, float(matrix_goal_parent[row][column]))
            goal_node.SetMatrixTransformToParent(matrix)
    except (TypeError, ValueError, IndexError) as exc:
        return False, f"Invalid TCP goal matrix: {exc}", goal_node
    return True, "Updated the provisional TCP goal transform.", goal_node


def solve_moveit_tcp_goal(
    *,
    seed_joint_positions_si: Optional[Mapping[str, float]] = None,
):
    """Solve the current goal probe through the configured MoveIt IK plugin."""
    logic, robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False
    )
    if error or logic is None or robot_node is None:
        return False, error or "TCP goal control is unavailable.", {}
    try:
        kwargs = {
            "robotmodel": robot_node,
            "tipLink": ROS2_TOOL_TCP_LINK,
        }
        if seed_joint_positions_si is not None:
            kwargs["seedJointValues"] = joint_si_vector(
                seed_joint_positions_si
            )
        solution = logic.computeIKWithMoveIt(**kwargs)
    except Exception as exc:
        return False, f"MoveIt IK request failed: {exc}", {}
    if not solution:
        return (
            False,
            "MoveIt found no collision-aware IK solution for the requested TCP pose.",
            {},
        )
    joint_names = [str(name) for name in robot_node.GetJoints()]
    if len(joint_names) != len(solution):
        return False, "MoveIt IK returned a joint-count mismatch.", {}
    by_name = dict(zip(joint_names, map(float, solution)))
    missing = [name for name in ROS2_JOINT_SI_ORDER if name not in by_name]
    if missing:
        return False, "MoveIt IK omitted: " + ", ".join(missing), {}
    ordered = {name: by_name[name] for name in ROS2_JOINT_SI_ORDER}
    return (
        True,
        f"MoveIt IK solved {ROS2_TOOL_TCP_LINK} with {len(ordered)} joints.",
        ordered,
    )


def _moveit_trajectory_result(trajectory) -> MoveItCartesianResult:
    ok, message = _trajectory_motion_summary(trajectory)
    if not ok:
        return MoveItCartesianResult(False, message)
    joint_trajectory = trajectory.GetJointTrajectory()
    names = [str(name) for name in joint_trajectory.GetJointNames()]
    missing = [name for name in ROS2_JOINT_SI_ORDER if name not in names]
    if missing:
        return MoveItCartesianResult(
            False,
            "MoveIt trajectory omitted: " + ", ".join(missing),
        )
    waypoints: list[dict[str, float]] = []
    times: list[float] = []
    for point in joint_trajectory.GetPoints():
        values = [float(value) for value in point.GetPositions()]
        if len(values) != len(names):
            return MoveItCartesianResult(
                False,
                "MoveIt returned a malformed joint point.",
            )
        by_name = dict(zip(names, values))
        waypoints.append({name: by_name[name] for name in ROS2_JOINT_SI_ORDER})
        times.append(_trajectory_time_seconds(point))
    return MoveItCartesianResult(
        True,
        message,
        fraction=1.0,
        waypoint_joint_vectors_si=tuple(waypoints),
        waypoint_times_sec=tuple(times),
    )


def plan_moveit_joint_goal(
    *,
    start_joint_positions_si: Optional[Mapping[str, float]] = None,
    goal_joint_positions_si: Optional[Mapping[str, float]] = None,
    refresh_planning_scene: bool = True,
    planning_attempts: Optional[int] = None,
    allowed_planning_time_sec: float = 10.0,
    planner_context: str = "",
) -> MoveItCartesianResult:
    """Plan one joint goal with explicit DENTOBOT state ownership.

    Routine Step 6 calls must provide both mappings. The legacy no-argument
    form remains available to the generic expert widget, but it intentionally
    retains that widget's current-state semantics and is not accepted as Step 6
    task evidence.
    """
    attempt_count = (
        ROS2_MOVEIT_JOINT_PLAN_ATTEMPTS
        if planning_attempts is None
        else max(1, int(planning_attempts))
    )
    allowed_time = max(0.1, float(allowed_planning_time_sec))
    logic, robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False,
        require_goal=False,
    )
    if error or logic is None or robot_node is None:
        return MoveItCartesianResult(False, error or "MoveIt context is unavailable.")
    explicit_start = start_joint_positions_si is not None
    explicit_goal = goal_joint_positions_si is not None
    explicit_context = str(planner_context or "explicit_joint_state")
    if explicit_start != explicit_goal:
        return MoveItCartesianResult(
            False,
            "Explicit MoveIt planning requires both start and goal joint vectors.",
        )
    if explicit_goal:
        try:
            joint_diagnostic = moveit_joint_goal_diagnostics(
                start_joint_positions_si,
                goal_joint_positions_si,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return MoveItCartesianResult(False, f"MoveIt start/goal vector is invalid: {exc}")
        submitted_start = dict(joint_diagnostic["start"])
        requested_goal = dict(joint_diagnostic["requested_goal"])
        submitted_goal = dict(joint_diagnostic["submitted_goal"])
        start_values = [submitted_start[name] for name in ROS2_JOINT_SI_ORDER]
        goal_values = [submitted_goal[name] for name in ROS2_JOINT_SI_ORDER]
        per_joint_delta = dict(joint_diagnostic["effective_deltas"])
        maximum_delta = float(joint_diagnostic["maximum_delta"])
        maximum_delta_joint = str(joint_diagnostic["maximum_joint"])
        raw_maximum_delta = float(joint_diagnostic["raw_maximum_delta"])
        raw_maximum_delta_joint = str(joint_diagnostic["raw_maximum_joint"])
        continuous_adjustments = dict(
            joint_diagnostic["continuous_adjustments"]
        )
        meaningfully_distinct = any(
            delta
            > (
                ROS2_MONITORED_PRISMATIC_TOLERANCE_M
                if "Slider" in name
                else ROS2_MONITORED_REVOLUTE_TOLERANCE_RAD
            )
            for name, delta in per_joint_delta.items()
        )
        monitored_start = monitored_joint_positions_si()
        monitored_error = None
        if monitored_start:
            monitored_error, _mismatched = _joint_state_error(
                submitted_start, monitored_start
            )
        if not meaningfully_distinct:
            return MoveItCartesianResult(
                False,
                "Rejected an accidental equal start/goal request: Task Home and "
                "PreEntry IK are indistinguishable within the monitored-state tolerances.",
                submitted_start_joint_positions_si=submitted_start,
                submitted_goal_joint_positions_si=submitted_goal,
                requested_goal_joint_positions_si=requested_goal,
                monitored_start_joint_positions_si=monitored_start or None,
                per_joint_start_goal_delta=per_joint_delta,
                maximum_start_goal_delta=maximum_delta,
                maximum_start_goal_delta_joint=maximum_delta_joint,
                raw_maximum_start_goal_delta=raw_maximum_delta,
                raw_maximum_start_goal_delta_joint=raw_maximum_delta_joint,
                continuous_joint_wrap_adjustments=continuous_adjustments,
                maximum_monitored_start_error=monitored_error,
                planner_start_source=explicit_context,
            )
    else:
        if not getattr(logic, "last_ik_solution", None):
            return MoveItCartesianResult(
                False,
                "Solve a distinct TCP IK goal before planning.",
            )
        start_values = []
        goal_values = [float(value) for value in logic.last_ik_solution]
        submitted_start = None
        submitted_goal = None
        requested_goal = None
        monitored_start = monitored_joint_positions_si()
        per_joint_delta = None
        maximum_delta = None
        maximum_delta_joint = ""
        raw_maximum_delta = None
        raw_maximum_delta_joint = ""
        continuous_adjustments = None
        monitored_error = None
    parameter_node = logic.getParameterNode()
    try:
        import slicer

        motion_node = slicer.mrmlScene.GetNodeByID(parameter_node.motionControlNodeID)
    except Exception:
        motion_node = None
    if motion_node is None:
        return MoveItCartesianResult(False, "MoveIt motion-control node is unavailable.")
    try:
        # Refresh republishes SlicerROS2 collision objects asynchronously. Do
        # not plan against a scene that is still changing: MoveIt can otherwise
        # find a path against the old world and invalidate it after newer
        # objects arrive in the response-validation adapter.
        if refresh_planning_scene:
            logic.RefreshMoveItPlanningScene(robot_node)
            deadline = time.monotonic() + ROS2_MOVEIT_PLANNING_SCENE_SETTLE_SEC
            while time.monotonic() < deadline:
                try:
                    import slicer

                    slicer.app.processEvents()
                except Exception:
                    pass
                ros_logic = get_ros2_logic()
                if ros_logic is not None:
                    try:
                        ros_logic.Spin()
                    except Exception:
                        pass
                time.sleep(0.02)
        last_result = MoveItCartesianResult(
            False, "MoveIt did not attempt joint-goal planning."
        )
        for attempt in range(1, attempt_count + 1):
            if explicit_start:
                planner = getattr(
                    motion_node, "PlanMoveItTrajectoryFromState", None
                )
                if planner is None:
                    return MoveItCartesianResult(
                        False,
                        "The loaded SlicerROS2 build lacks explicit-start planning; "
                        "rebuild/restart the module before Step 6.5.",
                        submitted_start_joint_positions_si=submitted_start,
                        submitted_goal_joint_positions_si=submitted_goal,
                        requested_goal_joint_positions_si=requested_goal,
                        monitored_start_joint_positions_si=monitored_start or None,
                        per_joint_start_goal_delta=per_joint_delta,
                        maximum_start_goal_delta=maximum_delta,
                        maximum_start_goal_delta_joint=maximum_delta_joint,
                        raw_maximum_start_goal_delta=raw_maximum_delta,
                        raw_maximum_start_goal_delta_joint=raw_maximum_delta_joint,
                        continuous_joint_wrap_adjustments=continuous_adjustments,
                        maximum_monitored_start_error=monitored_error,
                        planner_start_source=explicit_context,
                    )
                trajectory = planner(
                    ROS2_PLANNING_GROUP,
                    list(ROS2_JOINT_SI_ORDER),
                    start_values,
                    goal_values,
                    0.2,
                    0.2,
                    allowed_time,
                )
            else:
                trajectory = motion_node.PlanMoveItTrajectory(
                    ROS2_PLANNING_GROUP,
                    goal_values,
                    0.2,
                    0.2,
                    allowed_time,
                )
            native_plan_message = str(
                getattr(motion_node, "GetLastJointPlanMessage", lambda: "")()
                or ""
            )
            trajectory_result = _moveit_trajectory_result(trajectory)
            last_result = replace(
                trajectory_result,
                message=(
                    trajectory_result.message
                    + (
                        " " + native_plan_message
                        if native_plan_message
                        and not trajectory_result.success
                        else ""
                    )
                ),
                submitted_start_joint_positions_si=submitted_start,
                submitted_goal_joint_positions_si=submitted_goal,
                requested_goal_joint_positions_si=requested_goal,
                monitored_start_joint_positions_si=monitored_start or None,
                per_joint_start_goal_delta=per_joint_delta,
                maximum_start_goal_delta=maximum_delta,
                maximum_start_goal_delta_joint=maximum_delta_joint,
                raw_maximum_start_goal_delta=raw_maximum_delta,
                raw_maximum_start_goal_delta_joint=raw_maximum_delta_joint,
                continuous_joint_wrap_adjustments=continuous_adjustments,
                maximum_monitored_start_error=monitored_error,
                planner_start_source=(
                    explicit_context if explicit_start else "moveit_current_legacy"
                ),
                native_planner_message=native_plan_message,
            )
            if last_result.success:
                if attempt == 1:
                    return last_result
                return replace(
                    last_result,
                    message=(
                        f"{last_result.message} Stable-scene planning succeeded on "
                        f"bounded attempt {attempt}/{attempt_count}."
                    ),
                )
            if attempt < attempt_count:
                time.sleep(ROS2_MOVEIT_PLANNING_SCENE_SETTLE_SEC)
        ownership_evidence = ""
        if explicit_start:
            ownership_evidence = (
                f" Submitted explicit planner context={explicit_context}; "
                f"largest effective start/goal joint delta="
                f"{maximum_delta:.6g} on {maximum_delta_joint}"
                + (
                    f"; raw largest delta={raw_maximum_delta:.6g} on "
                    f"{raw_maximum_delta_joint}"
                    if raw_maximum_delta is not None
                    else ""
                )
                + (
                    "; normalized continuous joint representation: "
                    + ", ".join(
                        f"{name} {adjustment:+.6g} rad"
                        for name, adjustment in continuous_adjustments.items()
                    )
                    if continuous_adjustments
                    else ""
                )
                + (
                    f", maximum monitored/start error={monitored_error:.6g}."
                    if monitored_error is not None
                    else "; monitored start was unavailable."
                )
            )
        return replace(
            last_result,
            success=False,
            message=(
                f"MoveIt joint-goal planning failed after "
                f"{attempt_count} stable-scene attempt(s): "
                f"{last_result.message}{ownership_evidence}"
            ),
        )
    except Exception as exc:
        return MoveItCartesianResult(
            False,
            f"MoveIt goal planning failed: {exc}",
            submitted_start_joint_positions_si=submitted_start,
            submitted_goal_joint_positions_si=submitted_goal,
            requested_goal_joint_positions_si=requested_goal,
            monitored_start_joint_positions_si=monitored_start or None,
            per_joint_start_goal_delta=per_joint_delta,
            maximum_start_goal_delta=maximum_delta,
            maximum_start_goal_delta_joint=maximum_delta_joint,
            raw_maximum_start_goal_delta=raw_maximum_delta,
            raw_maximum_start_goal_delta_joint=raw_maximum_delta_joint,
            continuous_joint_wrap_adjustments=continuous_adjustments,
            maximum_monitored_start_error=monitored_error,
            planner_start_source=(
                explicit_context if explicit_start else "moveit_current_legacy"
            ),
        )


def check_moveit_static_joint_state(
    positions_si: Mapping[str, float],
    *,
    timeout_sec: float = 2.0,
) -> tuple[bool, str, bool]:
    """Query one explicit state against MoveIt's synchronized PlanningScene.

    Returns ``(valid, message, authoritative)``. The query is read-only and
    never changes the ROS current state or the translucent goal robot.
    """

    logic, _robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False,
        require_goal=False,
    )
    if error or logic is None:
        return False, error or "MoveIt context is unavailable.", False
    try:
        values = joint_si_vector(positions_si)
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"Static state vector is invalid: {exc}", False
    parameter_node = logic.getParameterNode()
    try:
        import slicer

        motion_node = slicer.mrmlScene.GetNodeByID(
            parameter_node.motionControlNodeID
        )
    except Exception:
        motion_node = None
    if motion_node is None:
        return False, "MoveIt motion-control node is unavailable.", False
    checker = getattr(motion_node, "CheckMoveItStateValidity", None)
    if checker is None:
        return (
            False,
            "The loaded SlicerROS2 build lacks explicit state-validity queries; "
            "rebuild/restart it before Step 6.3.",
            False,
        )
    try:
        valid = bool(
            checker(
                ROS2_PLANNING_GROUP,
                list(ROS2_JOINT_SI_ORDER),
                values,
                float(timeout_sec),
            )
        )
        message = str(motion_node.GetLastStateValidityMessage() or "")
    except Exception as exc:
        return False, f"MoveIt state-validity query failed: {exc}", False
    lowered = message.lower()
    authoritative = not any(
        token in lowered
        for token in (
            "unavailable",
            "timed out",
            "null response",
            "ros node",
            "empty or mismatched",
        )
    )
    return valid, message or ("MoveIt state is valid." if valid else "MoveIt state is invalid."), authoritative


def compute_moveit_static_tcp_pose_base_mm(
    positions_si: Mapping[str, float],
    *,
    timeout_sec: float = 2.0,
) -> tuple[bool, str, Optional[tuple[float, float, float]]]:
    """Return MoveIt FK for the provisional drill-tip frame without mutation."""

    logic, _robot_node, _goal_node, error = _dentobot_native_motion_context(
        initialize_goal=False,
        require_goal=False,
    )
    if error or logic is None:
        return False, error or "MoveIt context is unavailable.", None
    try:
        values = joint_si_vector(positions_si)
    except (KeyError, TypeError, ValueError) as exc:
        return False, f"FK state vector is invalid: {exc}", None
    parameter_node = logic.getParameterNode()
    try:
        import slicer

        motion_node = slicer.mrmlScene.GetNodeByID(
            parameter_node.motionControlNodeID
        )
    except Exception:
        motion_node = None
    if motion_node is None:
        return False, "MoveIt motion-control node is unavailable.", None
    compute_fk = getattr(motion_node, "ComputeMoveItForwardKinematics", None)
    if compute_fk is None:
        return (
            False,
            "The loaded SlicerROS2 build lacks explicit-state MoveIt FK; "
            "rebuild/restart it before Step 6.3.",
            None,
        )
    try:
        matrix = compute_fk(
            ROS2_PLANNING_GROUP,
            list(ROS2_JOINT_SI_ORDER),
            values,
            ROS2_TOOL_TCP_LINK,
            float(timeout_sec),
        )
        message = str(motion_node.GetLastForwardKinematicsMessage() or "")
        if not message.startswith("MoveIt FK returned"):
            return False, message or "MoveIt FK returned no authoritative pose.", None
        position = tuple(float(matrix.GetElement(index, 3)) for index in range(3))
    except Exception as exc:
        return False, f"MoveIt FK query failed: {exc}", None
    if len(position) != 3 or not all(isfinite(value) for value in position):
        return False, "MoveIt FK returned a non-finite TCP position.", None
    return True, message, position


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
        # SlicerROS2 derives moveit_msgs/CollisionObject.id directly from the
        # source model node's name.  The hidden proxy must therefore use the
        # canonical audited object ID, not a UI-oriented display label.
        proxy = slicer.mrmlScene.AddNewNodeByClass(
            "vtkMRMLModelNode", source_name
        )
        proxy.SetAttribute(ROS2_OBSTACLE_PROXY_ATTRIBUTE, "true")
        proxy.SetAttribute(ROS2_OBSTACLE_SOURCE_ATTRIBUTE, source_id)
    prior_published_id = str(
        proxy.GetAttribute(ROS2_OBSTACLE_PUBLISHED_ID_ATTRIBUTE)
        or proxy.GetName()
        or ""
    ).strip()
    if prior_published_id and prior_published_id != source_name:
        # Remove a collision object published by an older module revision (or
        # before a source rename) before reusing the proxy under its canonical
        # ID. PublishRemove also derives the ID from the model-node name.
        try:
            publisher = motion_logic._getCollisionObjectPublisher(
                robot_node, create=False
            )
            if publisher is not None:
                proxy.SetName(prior_published_id)
                publisher.SetFrameId(ROS2_FIXED_FRAME)
                publisher.PublishRemove(proxy)
        except Exception:
            # The canonical replacement below is still authoritative.  A
            # clean runtime starts without the obsolete ID, while an active
            # runtime will also discard it when the transient robot is torn
            # down.  Do not block current publication on best-effort cleanup.
            pass
        finally:
            proxy.SetName(source_name)
    else:
        proxy.SetName(source_name)
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
    proxy.SetAttribute(ROS2_OBSTACLE_PUBLISHED_ID_ATTRIBUTE, source_name)
    mark_slicer_ros2_runtime_nodes_transient()
    return True, ""


def acknowledge_moveit_collision_scene(
    *,
    expected_objects: Sequence[Mapping[str, object]],
    current_joint_positions_si: Mapping[str, float],
    timeout_sec: float = ROS2_TASK_GUARD_SCENE_SYNC_TIMEOUT_SEC,
) -> dict[str, object]:
    """Read back collision IDs/poses/bounds from the guard's PlanningScene.

    Publishing a CollisionObject only proves that the local publish call
    returned.  This bounded handshake sends the unchanged current simulation
    state through the guard and compares the guard's monitored MoveIt world
    against the exact prepared payload manifest.
    """

    expected_by_id = {
        str(record.get("outgoing_collision_object_id") or ""): record
        for record in expected_objects
    }
    expected_by_id.pop("", None)
    if not expected_by_id:
        return {
            "status": "Mismatch",
            "reason": "No expected collision objects were supplied.",
            "acknowledged_object_ids": [],
            "mismatches": ["empty expected object set"],
        }
    deadline = time.monotonic() + max(0.1, float(timeout_sec))
    last_status = None
    last_mismatches = ["PlanningScene readback has not arrived."]
    while time.monotonic() < deadline:
        # A rejected unchanged state still carries valid read-only world
        # evidence.  It is not treated as an accepted motion command here.
        apply_joint_positions_si_to_motion_control(current_joint_positions_si)
        status = joint_command_status(max_age_sec=1.0)
        if status is None:
            time.sleep(0.05)
            continue
        last_status = status
        if not status.world_object_evidence_present:
            return {
                "status": "RuntimeUpgradeRequired",
                "reason": (
                    "The running collision guard predates per-object PlanningScene "
                    "evidence. Restart the external DENTOBOT simulation stack so "
                    "it uses the newly built collision_guard binary, then reconnect."
                ),
                "acknowledged_object_ids": [],
                "mismatches": [],
            }
        runtime_by_id = {
            str(record.get("id") or ""): record for record in status.world_objects
        }
        mismatches: list[str] = []
        for object_id, expected in expected_by_id.items():
            observed = runtime_by_id.get(object_id)
            if observed is None:
                mismatches.append(f"missing runtime object {object_id}")
                continue
            expected_bounds_mm = tuple(
                float(value)
                for value in expected.get("outgoing_bounds_base_link_mm", ())
            )
            observed_bounds_m = observed.get("bounds_base_link_m")
            if len(expected_bounds_mm) != 6 or observed_bounds_m is None:
                mismatches.append(f"missing comparable bounds for {object_id}")
                continue
            expected_bounds_m = tuple(value * 0.001 for value in expected_bounds_mm)
            if any(
                abs(expected_value - float(observed_value)) > 1e-6
                for expected_value, observed_value in zip(
                    expected_bounds_m, observed_bounds_m
                )
            ):
                mismatches.append(f"runtime bounds differ for {object_id}")
            if int(observed.get("shape_count", 0)) < 1:
                mismatches.append(f"runtime object {object_id} has no shape")
        if mismatches:
            missing_ids = sorted(set(expected_by_id).difference(runtime_by_id))
            unexpected_ids = sorted(set(runtime_by_id).difference(expected_by_id))
            legacy_prefix = "[Step 6] MoveIt obstacle - "
            legacy_proxy_ids = {
                f"{legacy_prefix}{object_id}" for object_id in expected_by_id
            }
            if missing_ids and set(runtime_by_id) == legacy_proxy_ids:
                mismatches = [
                    "runtime uses obsolete display-prefixed collision IDs; "
                    "restart Slicer with the current DENTOWorkflow source"
                ]
            elif missing_ids:
                missing_preview = ", ".join(missing_ids[:5])
                unexpected_preview = ", ".join(unexpected_ids[:5])
                mismatches = [
                    f"runtime collision ID set differs: expected "
                    f"{len(expected_by_id)}, observed {len(runtime_by_id)}; "
                    f"missing [{missing_preview}]"
                    + (
                        f"; unexpected [{unexpected_preview}]"
                        if unexpected_preview
                        else ""
                    )
                ]
            else:
                mismatches = mismatches[:5]
        last_mismatches = mismatches
        if not mismatches:
            unexpected = sorted(set(runtime_by_id).difference(expected_by_id))
            return {
                "status": "Acknowledged",
                "reason": (
                    "The collision guard's monitored MoveIt PlanningScene "
                    "contains every prepared object with matching mesh bounds."
                ),
                "acknowledged_object_ids": sorted(expected_by_id),
                "unexpected_object_ids": unexpected,
                "world_object_count": int(status.world_object_count),
                "objects": [runtime_by_id[key] for key in sorted(expected_by_id)],
            }
        time.sleep(0.1)
    return {
        "status": "Mismatch",
        "reason": (
            "MoveIt PlanningScene readback did not match the prepared collision "
            "payload before the bounded timeout."
        ),
        "acknowledged_object_ids": (
            sorted(str(record.get("id") or "") for record in last_status.world_objects)
            if last_status is not None
            else []
        ),
        "world_object_count": (
            int(last_status.world_object_count) if last_status is not None else 0
        ),
        "mismatches": last_mismatches,
    }


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
    global _native_goal_transform
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
    if motion_logic is not None and _native_goal_transform is not None:
        try:
            motion_logic.ExitControlMode(_native_goal_transform)
        except Exception:
            pass
        _native_goal_transform = None
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
    global _task_config_publisher, _task_command_publisher
    global _task_status_subscriber, _task_status_observer
    global _last_task_status, _last_task_status_at, _last_task_config_json
    global _native_goal_transform
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
    task_subscriber = _task_status_subscriber
    if task_subscriber is not None and _task_status_observer is not None:
        try:
            task_subscriber.RemoveObserver(_task_status_observer)
        except Exception:
            pass
    if ros_node is not None and task_subscriber is not None:
        task_subscriber_id = task_subscriber.GetID()
        try:
            ros_node.RemoveAndDeleteSubscriberNode(ROS2_TASK_JOINT_STATUS_TOPIC)
        except Exception:
            pass
        finally:
            _remove_ros2_node_reference(ros_node, "subscriber", task_subscriber_id)
    for topic, publisher in (
        (ROS2_TASK_GUARD_CONFIG_TOPIC, _task_config_publisher),
        (ROS2_TASK_JOINT_COMMAND_TOPIC, _task_command_publisher),
    ):
        if ros_node is None or publisher is None:
            continue
        publisher_id = publisher.GetID()
        try:
            ros_node.RemoveAndDeletePublisherNode(topic)
        except Exception:
            pass
        finally:
            _remove_ros2_node_reference(ros_node, "publisher", publisher_id)
    _status_subscriber = None
    _status_observer = None
    _last_status = SimulationStackStatus(RuntimeState.OFFLINE, reason="No status received.")
    _last_status_at = 0.0
    _joint_status_subscriber = None
    _joint_status_observer = None
    _last_joint_status = None
    _last_joint_status_at = 0.0
    _task_config_publisher = None
    _task_command_publisher = None
    _task_status_subscriber = None
    _task_status_observer = None
    _last_task_status = None
    _last_task_status_at = 0.0
    _last_task_config_json = ""
    _native_goal_transform = None
