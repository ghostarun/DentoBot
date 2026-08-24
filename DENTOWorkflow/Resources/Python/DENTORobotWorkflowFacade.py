"""UI-independent orchestration boundary for DENTOBOT Step 6 simulation.

The legacy workflow panel and the application shell both call this façade.
Robot geometry, ROS 2, MoveIt, collision, and planning remain implemented by
the existing logic and bridge modules; this class only coordinates them and
returns structured presentation results.  It intentionally exposes no
hardware execution path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import degrees, isfinite
from typing import Any, Callable, Mapping, Optional, Sequence

import DENTOROS2Bridge as _default_bridge
from DENTORobotPlacement import joint_positions_si_from_display


JOINT_DISPLAY_FIELDS = (
    "robotJoint1Deg",
    "robotJoint2Mm",
    "robotJoint3Deg",
    "robotJoint4Mm",
    "robotJoint5Deg",
    "robotJoint6Deg",
)
JOINT_LIMIT_FIELDS = (
    "joint_1",
    "joint_2",
    "joint_3",
    "joint_4",
    "joint_5",
    "joint_6",
)
JOINT_DISPLAY_UNITS = ("deg", "mm", "deg", "mm", "deg", "deg")
JOINT_NAMES = tuple(_default_bridge.ROS2_JOINT_SI_ORDER)


@dataclass(frozen=True)
class RobotActionResult:
    """One deterministic façade action outcome suitable for either GUI."""

    success: bool
    code: str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)
    payload: Any = None


@dataclass(frozen=True)
class RobotCapabilities:
    """Read-only runtime capability snapshot; never saved with an MRML case."""

    simulation_only: bool
    stack_state: str
    description_ready: bool
    planning_ready: bool
    single_joint_state_source: bool
    connected: bool
    robot_loaded: bool
    move_group_available: bool
    planning_group: str
    tcp_link: str
    ik_available: bool
    collision_check_available: bool
    planning_scene_synchronized: bool
    planning_scene_object_count: int
    reason: str = ""


@dataclass(frozen=True)
class RobotWorkflowState:
    """Operator-unit view of the current Step 6 state."""

    scene_kind: str
    joint_names: tuple[str, ...]
    joint_display_values: tuple[float, ...]
    joint_display_units: tuple[str, ...]
    joint_positions_si: Mapping[str, float]
    base_node_id: str
    base_locked: bool
    ros_motion_active: bool
    has_motion_plan: bool
    preview_active: bool


class DENTORobotWorkflowFacade:
    """Coordinate Step 6 services without depending on DENTOWorkflow widgets."""

    def __init__(
        self,
        logic,
        parameter_node_provider: Callable[[], Any],
        *,
        bridge=None,
    ) -> None:
        self._logic = logic
        self._parameter_node_provider = parameter_node_provider
        self._bridge = bridge or _default_bridge
        self._motion_plan = None
        self._preview_timer = None
        self._preview_index = 0
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False

    def setLogic(self, logic) -> None:
        self._logic = logic

    @property
    def motionPlan(self):
        return self._motion_plan

    @property
    def previewActive(self) -> bool:
        return self._preview_timer is not None

    def clearTransientState(self) -> None:
        self.stopPreview()
        self._motion_plan = None
        self._planning_scene_object_count = 0
        self._planning_scene_synchronized = False

    def _parameter_node(self):
        return self._parameter_node_provider()

    def _require_context(self):
        parameter_node = self._parameter_node()
        if parameter_node is None:
            raise RuntimeError("Step 6 parameter node is unavailable.")
        if self._logic is None:
            raise RuntimeError("DENTOBOT workflow logic is unavailable.")
        return parameter_node

    def _scene_kind(self, parameter_node) -> str:
        imported = bool(parameter_node.step6PlanningContextImported)
        phantom = bool(self._logic.draftPhantomModelNodes())
        if imported and phantom:
            return "conflict"
        if imported:
            return "case"
        if phantom:
            return "phantom"
        return "none"

    @staticmethod
    def _display_values(parameter_node) -> tuple[float, ...]:
        return tuple(float(getattr(parameter_node, name)) for name in JOINT_DISPLAY_FIELDS)

    @staticmethod
    def _positions_si(display_values: Sequence[float]) -> dict[str, float]:
        return joint_positions_si_from_display(*display_values)

    @staticmethod
    def _write_display_values(parameter_node, display_values: Sequence[float]) -> None:
        modify_token = (
            parameter_node.StartModify()
            if hasattr(parameter_node, "StartModify")
            else None
        )
        try:
            for field_name, value in zip(JOINT_DISPLAY_FIELDS, display_values):
                setattr(parameter_node, field_name, float(value))
        finally:
            if modify_token is not None:
                parameter_node.EndModify(modify_token)

    @staticmethod
    def _display_values_from_si(positions_si: Mapping[str, float]) -> tuple[float, ...]:
        return (
            degrees(float(positions_si[JOINT_NAMES[0]])),
            float(positions_si[JOINT_NAMES[1]]) * 1000.0,
            degrees(float(positions_si[JOINT_NAMES[2]])),
            float(positions_si[JOINT_NAMES[3]]) * 1000.0,
            degrees(float(positions_si[JOINT_NAMES[4]])),
            degrees(float(positions_si[JOINT_NAMES[5]])),
        )

    def capabilities(self) -> RobotCapabilities:
        parameter_node = self._parameter_node()
        stack_status = self._bridge.simulation_stack_status()
        connected = bool(
            parameter_node
            and self._logic
            and self._logic.isRos2MotionControlActive(
                parameter_node.robotBaseTransform
            )
        )
        mrml_robot_loaded = bool(self._logic and self._logic.robotModelNodes())
        planning_ready = bool(stack_status.planning_ready)
        return RobotCapabilities(
            simulation_only=True,
            stack_state=str(getattr(stack_status.state, "value", stack_status.state)),
            description_ready=bool(stack_status.description_ready),
            planning_ready=planning_ready,
            single_joint_state_source=stack_status.joint_state_publisher_count == 1,
            connected=connected,
            robot_loaded=connected or mrml_robot_loaded,
            move_group_available=planning_ready,
            planning_group=self._bridge.ROS2_PLANNING_GROUP,
            tcp_link=self._bridge.ROS2_TOOL_TCP_LINK,
            ik_available=connected and planning_ready,
            collision_check_available=connected and planning_ready,
            planning_scene_synchronized=self._planning_scene_synchronized,
            planning_scene_object_count=self._planning_scene_object_count,
            reason=str(stack_status.reason or ""),
        )

    def currentRobotState(self) -> RobotWorkflowState:
        parameter_node = self._require_context()
        display_values = self._display_values(parameter_node)
        base = parameter_node.robotBaseTransform
        base_id = base.GetID() if base is not None and hasattr(base, "GetID") else ""
        return RobotWorkflowState(
            scene_kind=self._scene_kind(parameter_node),
            joint_names=JOINT_NAMES,
            joint_display_values=display_values,
            joint_display_units=JOINT_DISPLAY_UNITS,
            joint_positions_si=self._positions_si(display_values),
            base_node_id=base_id,
            base_locked=bool(parameter_node.robotBaseMountLocked),
            ros_motion_active=bool(
                base is not None and self._logic.isRos2MotionControlActive(base)
            ),
            has_motion_plan=bool(
                self._motion_plan is not None
                and getattr(self._motion_plan, "success", False)
            ),
            preview_active=self._preview_timer is not None,
        )

    def connect(self, *, open_motion_module: bool = False) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            scene_kind = self._scene_kind(parameter_node)
            if scene_kind not in {"case", "phantom"}:
                return RobotActionResult(
                    False,
                    "scene_required",
                    "Choose a Step 6 case or draft phantom before connecting.",
                )
            base = self._logic.ensureRobotBaseTransform(
                parameter_node.robotBaseTransform
            )
            parameter_node.robotBaseTransform = base
            phantom_models = self._logic.draftPhantomModelNodes()
            if phantom_models:
                self._logic.positionRobotBaseNearResearchPhantom(base, phantom_models)
            mrml_models = self._logic.robotModelNodes()
            robot_node, error = self._bridge.connect_dentobot_motion_control(
                base,
                hide_mrml_robot=bool(mrml_models),
                mrml_robot_models=mrml_models,
                open_motion_module=bool(open_motion_module),
                start_stack_if_needed=False,
            )
            if error or robot_node is None:
                return RobotActionResult(
                    False,
                    "connect_failed",
                    error or "ROS 2 robot node was not created.",
                )
            self._planning_scene_synchronized = False
            return RobotActionResult(
                True,
                "connected",
                "Connected the simulation-only SlicerROS2 robot and MoveIt planning group.",
                payload=robot_node,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "connect_failed", str(exc))

    def disconnect(self) -> RobotActionResult:
        try:
            self.stopPreview()
            mrml_models = self._logic.robotModelNodes() if self._logic else []
            ok, message = self._bridge.disconnect_dentobot_motion_control(mrml_models)
            if not ok:
                return RobotActionResult(False, "disconnect_failed", message)
            self._planning_scene_synchronized = False
            self._planning_scene_object_count = 0
            return RobotActionResult(
                True,
                "disconnected",
                message or "Disconnected the ROS 2 robot; local MRML meshes are visible.",
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "disconnect_failed", str(exc))

    def loadRobot(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) not in {"case", "phantom"}:
                return RobotActionResult(
                    False,
                    "scene_required",
                    "Choose a Step 6 case or draft phantom before loading the robot.",
                )
            base, models = self._logic.createOrUpdateRobotPlacement(
                parameter_node.robotBaseTransform,
                self._positions_si(self._display_values(parameter_node)),
            )
            parameter_node.robotBaseTransform = base
            phantom_models = self._logic.draftPhantomModelNodes()
            if phantom_models:
                self._logic.positionRobotBaseNearResearchPhantom(base, phantom_models)
            return RobotActionResult(
                True,
                "robot_loaded",
                f"Loaded or reused {len(models)} local robot link models.",
                details={"linkCount": len(models)},
                payload=(base, models),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "robot_load_failed", str(exc))

    def requestJointValue(self, joint_id: int | str, display_value: float) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if isinstance(joint_id, str):
                try:
                    index = JOINT_NAMES.index(joint_id)
                except ValueError:
                    return RobotActionResult(False, "unknown_joint", f"Unknown joint: {joint_id}")
            else:
                index = int(joint_id)
                if 1 <= index <= len(JOINT_NAMES):
                    index -= 1
            if index < 0 or index >= len(JOINT_NAMES):
                return RobotActionResult(False, "unknown_joint", f"Unknown joint index: {joint_id}")
            value = float(display_value)
            if not isfinite(value):
                return RobotActionResult(False, "invalid_joint_value", "Joint value must be finite.")
            limits = self._logic.getTaskJointLimits(parameter_node)
            limit = getattr(limits, JOINT_LIMIT_FIELDS[index])
            if value < limit.minimum or value > limit.maximum:
                return RobotActionResult(
                    False,
                    "joint_limit",
                    f"{JOINT_NAMES[index]} must remain within {limit.minimum:g} to {limit.maximum:g} {JOINT_DISPLAY_UNITS[index]}.",
                )
            prior_display = list(self._display_values(parameter_node))
            requested_display = list(prior_display)
            requested_display[index] = value
            self._write_display_values(parameter_node, requested_display)
            positions_si = self._positions_si(requested_display)
            base = parameter_node.robotBaseTransform
            if base is not None and self._logic.isRos2MotionControlActive(base):
                ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                    positions_si
                )
                if not ok:
                    accepted = self._bridge.last_accepted_joint_positions_si()
                    restored = (
                        self._display_values_from_si(accepted)
                        if accepted and all(name in accepted for name in JOINT_NAMES)
                        else tuple(prior_display)
                    )
                    self._write_display_values(parameter_node, restored)
                    return RobotActionResult(False, "joint_rejected", message)
            elif self._logic.robotLinkTransformNodes():
                self._logic.updateRobotJointPoses(positions_si)
            self._motion_plan = None
            return RobotActionResult(
                True,
                "joint_accepted",
                f"{JOINT_NAMES[index]} set to {value:g} {JOINT_DISPLAY_UNITS[index]}.",
                details={"jointIndex": index, "displayValue": value},
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "joint_update_failed", str(exc))

    def requestCurrentJointState(self) -> RobotActionResult:
        """Validate/publish values already written by MRML GUI binding."""
        try:
            parameter_node = self._require_context()
            requested_display = self._display_values(parameter_node)
            positions_si = self._positions_si(requested_display)
            base = parameter_node.robotBaseTransform
            if base is not None and self._logic.isRos2MotionControlActive(base):
                ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                    positions_si
                )
                if not ok:
                    accepted = self._bridge.last_accepted_joint_positions_si()
                    if accepted and all(name in accepted for name in JOINT_NAMES):
                        self._write_display_values(
                            parameter_node,
                            self._display_values_from_si(accepted),
                        )
                    return RobotActionResult(False, "joint_rejected", message)
            elif self._logic.robotLinkTransformNodes():
                self._logic.updateRobotJointPoses(positions_si)
            self._motion_plan = None
            return RobotActionResult(
                True,
                "joint_state_accepted",
                "Accepted the current six-joint simulation state.",
                payload=positions_si,
            )
        except (RuntimeError, ValueError, OSError, KeyError) as exc:
            return RobotActionResult(False, "joint_update_failed", str(exc))

    def setBasePose(self, matrix_world_ras_mm) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if parameter_node.robotBaseMountLocked:
                return RobotActionResult(False, "base_locked", "Unlock the robot base before moving it.")
            base = self._logic.ensureRobotBaseTransform(parameter_node.robotBaseTransform)
            parameter_node.robotBaseTransform = base
            base.SetAndObserveTransformNodeID(None)
            base.SetMatrixTransformToParent(matrix_world_ras_mm)
            self._planning_scene_synchronized = False
            self._motion_plan = None
            return RobotActionResult(True, "base_pose_updated", "Updated the robot base in world RAS millimetres.")
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_pose_failed", str(exc))

    def lockBase(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if self._scene_kind(parameter_node) not in {"case", "phantom"}:
                return RobotActionResult(False, "scene_required", "Choose a Step 6 scene before locking the base.")
            if not (self._logic.robotModelNodes() or self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform)):
                return RobotActionResult(False, "robot_required", "Load the ROS robot or local fallback before locking the base.")
            self._logic.setRobotBaseMountLocked(parameter_node, True)
            obstacle_count = 0
            if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                obstacle_count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
                self._planning_scene_object_count = obstacle_count
                self._planning_scene_synchronized = True
            return RobotActionResult(
                True,
                "base_locked",
                f"Base mount locked; {obstacle_count} MoveIt collision surface(s) synchronized.",
                details={"obstacleCount": obstacle_count},
            )
        except (RuntimeError, ValueError, OSError) as exc:
            try:
                self._logic.setRobotBaseMountLocked(self._parameter_node(), False)
            except Exception:
                pass
            return RobotActionResult(False, "base_lock_failed", str(exc))

    def unlockBase(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            self._logic.setRobotBaseMountLocked(parameter_node, False)
            self._planning_scene_synchronized = False
            self._motion_plan = None
            return RobotActionResult(True, "base_unlocked", "Base mount unlocked.")
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "base_unlock_failed", str(exc))

    def syncPlanningScene(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            if not self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
                return RobotActionResult(False, "ros_required", "Connect ROS 2 Motion Control before syncing collision objects.")
            count = self._logic.syncStep6MoveItPlanningScene(parameter_node)
            self._planning_scene_object_count = count
            self._planning_scene_synchronized = True
            return RobotActionResult(
                True,
                "planning_scene_synced",
                f"Synchronized {count} Step 6 collision surface(s) with MoveIt.",
                details={"obstacleCount": count},
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._planning_scene_synchronized = False
            return RobotActionResult(False, "planning_scene_failed", str(exc))

    def checkStateValidity(self) -> RobotActionResult:
        try:
            state = self.currentRobotState()
            if not state.ros_motion_active:
                return RobotActionResult(
                    True,
                    "draft_state_only",
                    "Local MRML state is available; MoveIt/FCL validity requires a ROS 2 connection.",
                    details={"authoritative": False},
                )
            status = self._bridge.joint_command_status()
            if status is None:
                return RobotActionResult(False, "status_unavailable", "No fresh MoveIt joint-validity status is available.")
            return RobotActionResult(
                bool(status.accepted),
                "state_valid" if status.accepted else "state_invalid",
                status.reason,
                details={
                    "authoritative": True,
                    "minimumClearanceMm": float(status.minimum_clearance_m) * 1000.0,
                    "minimumSelfDistanceMm": None if status.minimum_self_distance_m is None else float(status.minimum_self_distance_m) * 1000.0,
                    "minimumWorldDistanceMm": None if status.minimum_world_distance_m is None else float(status.minimum_world_distance_m) * 1000.0,
                    "firstBody": status.first_body,
                    "secondBody": status.second_body,
                    "worldObjectCount": status.world_object_count,
                },
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "state_check_failed", str(exc))

    def setTcpGoal(self, matrix_goal_parent) -> RobotActionResult:
        ok, message, goal_node = self._bridge.set_moveit_tcp_goal_matrix(
            matrix_goal_parent
        )
        return RobotActionResult(
            ok,
            "tcp_goal_updated" if ok else "tcp_goal_failed",
            message,
            payload=goal_node,
        )

    def ensureTcpGoal(self) -> RobotActionResult:
        ok, message, goal_node = self._bridge.ensure_moveit_tcp_goal_control()
        return RobotActionResult(
            ok,
            "tcp_goal_ready" if ok else "tcp_goal_failed",
            message,
            payload=goal_node,
        )

    def solveIk(self) -> RobotActionResult:
        ok, message, positions = self._bridge.solve_moveit_tcp_goal()
        return RobotActionResult(
            ok,
            "ik_solved" if ok else "ik_failed",
            message,
            payload=positions,
        )

    def planToGoal(self) -> RobotActionResult:
        result = self._bridge.plan_moveit_joint_goal()
        self._motion_plan = result if result.success else None
        return RobotActionResult(
            result.success,
            "goal_plan_ready" if result.success else "goal_plan_failed",
            result.message,
            details={"waypointCount": len(result.waypoint_joint_vectors_si)},
            payload=result,
        )

    def planAlongTrajectory(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            self.stopPreview()
            result = self._logic.planStep6TrajectoryMotion(parameter_node)
            self._motion_plan = result if result.success else None
            return RobotActionResult(
                result.success,
                "trajectory_plan_ready" if result.success else "trajectory_plan_failed",
                result.message,
                details={
                    "planner": result.planner,
                    "waypointCount": len(result.waypoint_joint_vectors_si),
                    "cartesianFraction": result.cartesian_fraction,
                },
                payload=result,
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._motion_plan = None
            return RobotActionResult(False, "trajectory_plan_failed", str(exc))

    def _apply_positions_si(self, positions_si: Mapping[str, float]) -> RobotActionResult:
        parameter_node = self._require_context()
        display_values = self._display_values_from_si(positions_si)
        prior_values = self._display_values(parameter_node)
        self._write_display_values(parameter_node, display_values)
        if self._logic.isRos2MotionControlActive(parameter_node.robotBaseTransform):
            ok, message = self._bridge.apply_joint_positions_si_to_motion_control(
                positions_si
            )
            if not ok:
                self._write_display_values(parameter_node, prior_values)
                return RobotActionResult(False, "preview_rejected", message)
        elif self._logic.robotLinkTransformNodes():
            self._logic.updateRobotJointPoses(dict(positions_si))
        return RobotActionResult(True, "preview_waypoint", "Applied simulated preview waypoint.")

    def previewPlan(
        self,
        *,
        interval_ms: int = 250,
        on_progress: Optional[Callable[[int, int], None]] = None,
        on_finished: Optional[Callable[[RobotActionResult], None]] = None,
    ) -> RobotActionResult:
        plan = self._motion_plan
        waypoints = tuple(getattr(plan, "waypoint_joint_vectors_si", ()) or ())
        if not plan or not getattr(plan, "success", False) or not waypoints:
            return RobotActionResult(False, "plan_required", "Create a successful simulation plan before previewing it.")
        try:
            import qt
        except ImportError:
            return RobotActionResult(False, "qt_unavailable", "Qt is unavailable for simulated preview timing.")
        self.stopPreview()
        self._preview_index = 0
        timer = qt.QTimer()
        timer.setInterval(max(20, int(interval_ms)))

        def advance() -> None:
            if self._preview_index >= len(waypoints):
                self.stopPreview()
                if on_finished:
                    on_finished(RobotActionResult(True, "preview_complete", "Simulated motion preview complete."))
                return
            result = self._apply_positions_si(waypoints[self._preview_index])
            if not result.success:
                self.stopPreview()
                if on_finished:
                    on_finished(result)
                return
            self._preview_index += 1
            if on_progress:
                on_progress(self._preview_index, len(waypoints))

        timer.timeout.connect(advance)
        timer.start()
        self._preview_timer = timer
        return RobotActionResult(True, "preview_started", f"Previewing {len(waypoints)} simulated waypoint(s).")

    def stopPreview(self) -> RobotActionResult:
        if self._preview_timer is not None:
            self._preview_timer.stop()
            self._preview_timer = None
        self._preview_index = 0
        return RobotActionResult(True, "preview_stopped", "Simulated preview stopped.")

    def generateWorkspaceCloud(self) -> RobotActionResult:
        try:
            parameter_node = self._require_context()
            model, report = self._logic.createOrUpdateRobotWorkspace(parameter_node)
            return RobotActionResult(
                True,
                "workspace_ready",
                f"Accepted {report.accepted_count}/{report.requested_count} deterministic workspace samples.",
                details={
                    "requestedCount": report.requested_count,
                    "acceptedCount": report.accepted_count,
                    "selfCollisionRejections": report.self_collision_rejections,
                    "environmentRejections": report.environment_rejections,
                    "excludedAabbPairs": report.excluded_aabb_pairs,
                },
                payload=(model, report),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            return RobotActionResult(False, "workspace_failed", str(exc))
