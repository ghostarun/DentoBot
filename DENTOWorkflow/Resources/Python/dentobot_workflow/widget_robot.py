"""Extracted Step 6 and robot UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from collections.abc import Mapping
from math import degrees, isfinite

from .runtime import *
from .workflow_progress import WorkflowProgress

from DENTOStep6State import JOINT_NAMES

from dentobot_workflow.widget_robot_shell import RobotShellWidgetMixin


from dentobot_workflow.widget_robot_placement import RobotPlacementWidgetMixin


from dentobot_workflow.widget_robot_scene import RobotSceneWidgetMixin


class RobotWidgetMixin(RobotSceneWidgetMixin, RobotPlacementWidgetMixin, RobotShellWidgetMixin):
    def _manualJogIdentityCurrent(self) -> bool:
        facade = getattr(self, "_robotWorkflowFacade", None)
        if facade is None:
            return False
        try:
            facade._manual_jog_current_identity(self._parameterNode)
        except (AttributeError, KeyError, OSError, RuntimeError, TypeError, ValueError):
            return False
        return True

    def _manualTaskHomeReviewControlState(self, live_scene, review_result):
        details = getattr(review_result, "details", {}) or {}
        if not isinstance(details, Mapping):
            details = {}
        staged = details.get("staged") is True
        identity_current = str(details.get("identityStatus") or "unknown") == "current"
        acceptance_status = str(details.get("acceptanceStatus") or "unknown")
        acceptance_uncertain = bool(details.get("acceptanceUncertainty"))
        success = bool(getattr(review_result, "success", False))
        setup_mode = str(details.get("setupMode") or "unknown")
        if setup_mode not in {"offline", "connected"}:
            setup_mode = "unknown"
        offline = setup_mode == "offline"
        connected = setup_mode == "connected"
        accepted = details.get("acceptedJointPositionsSi")
        candidate = details.get("candidateJointPositionsSi")
        try:
            candidate_valid = (
                isinstance(candidate, Mapping)
                and set(candidate) == set(JOINT_NAMES)
                and all(isfinite(float(candidate[joint])) for joint in JOINT_NAMES)
            )
            matches = (
                connected
                and
                isinstance(accepted, Mapping)
                and isinstance(candidate, Mapping)
                and set(accepted) == set(JOINT_NAMES)
                and set(candidate) == set(JOINT_NAMES)
                and all(
                    isfinite(float(accepted[joint]))
                    and isfinite(float(candidate[joint]))
                    and abs(
                        float(accepted[joint]) - float(candidate[joint])
                    ) <= 1.0e-12
                    for joint in JOINT_NAMES
                )
            )
        except (TypeError, ValueError, OverflowError):
            candidate_valid = False
            matches = False
        allowed_review_statuses = (
            {"review", "accepted", "configuration_saved"}
            if offline
            else {"review", "accepted"}
        )
        return {
            "group": bool(live_scene or offline or staged or setup_mode == "unknown"),
            "review": bool(
                ((live_scene and connected) or offline)
                and success
                and identity_current
                and not staged
                and acceptance_status in allowed_review_statuses
            ),
            "cancel": staged and not acceptance_uncertain,
            "accept": bool(
                ((live_scene and connected) or offline)
                and success
                and staged
                and identity_current
                and not acceptance_uncertain
                and acceptance_status == "review"
                and (candidate_valid if offline else matches if connected else False)
            ),
            "reconcile": bool(
                connected
                and live_scene
                and staged
                and acceptance_uncertain
            ),
        }




















































































    def _step6SceneKind(self) -> str:
        if not self._parameterNode or not self.logic:
            return "none"
        if (
            self._parameterNode.inputVolume
            and self._parameterNode.teethSegmentation
        ):
            return "case"
        return "none"

    def _step6RobotPresent(self) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        base = self._parameterNode.robotBaseTransform
        if self.logic.isRos2MotionControlActive(base):
            return True
        return bool(self.logic.robotModelNodes())

    def _showStep6CaseVolumeInSliceViewers(self) -> None:
        if not self._parameterNode:
            return
        volume = self._parameterNode.inputVolume
        if volume is None:
            return
        try:
            slicer.util.setSliceViewerLayers(background=volume, fit=True)
        except Exception:
            logging.debug("Could not set slice viewers to the Step 6 case volume.")

    def _applyStep6RecommendedView(self) -> None:
        if not hasattr(self, "ui"):
            return
        stage_entries = self._workflowStageEntries()
        last_stage = bool(
            stage_entries
            and int(self.ui.workflowStageComboBox.currentIndex)
            == len(stage_entries) - 1
        )
        if self._isStep3BActive():
            self._applyStep3BRecommendedView()
            return
        if not last_stage:
            return
        self._applyWorkflowViewPreset("recommended", updateStatus=False)
        self._updateWorkflowViewControls()

    def _confirmStep6SceneSwitch(self, target: str) -> bool:
        return target == "case"

    def _syncManualBaseCandidateGhost(self, reviewResult=None) -> str:
        details = getattr(reviewResult, "details", {}) or {}
        if not isinstance(details, Mapping):
            details = {}
        staged = bool(details.get("staged"))
        identity_current = str(details.get("identityStatus") or "unknown") == "current"
        candidate = details.get("candidateMatrixWorldRasMm")
        try:
            candidate = tuple(float(value) for value in candidate)
            valid = len(candidate) == 16 and all(
                math.isfinite(value) for value in candidate
            )
        except (TypeError, ValueError, OverflowError):
            candidate = ()
            valid = False
        logic = getattr(self, "logic", None)

        def clear_ghost() -> None:
            self._manualBaseCandidateGhostKey = None
            clear = getattr(logic, "clearManualBaseCandidateGhost", None)
            if callable(clear):
                clear()

        if not (staged and identity_current and valid):
            cache_initialized = hasattr(self, "_manualBaseCandidateGhostKey")
            if getattr(self, "_manualBaseCandidateGhostKey", None) is not None or not cache_initialized:
                clear_ghost()
            else:
                self._manualBaseCandidateGhostKey = None
            if staged and identity_current:
                return (
                    "Candidate visualization unavailable: staged matrix evidence is invalid; "
                    "the candidate remains unaccepted."
                )
            return ""

        base_fingerprint = ""
        parameter_node = getattr(self, "_parameterNode", None)
        base = getattr(parameter_node, "robotBaseTransform", None)
        fingerprint = getattr(logic, "robotBasePoseFingerprint", None)
        if callable(fingerprint) and base is not None:
            try:
                base_fingerprint = str(fingerprint(base) or "")
            except Exception:
                pass

        def node_id(node):
            get_id = getattr(node, "GetID", None)
            return (str(get_id() or "") or id(node)) if callable(get_id) else id(node)

        cache_key = (
            candidate,
            base_fingerprint,
            tuple(
                node_id(node) if node is not None else None
                for node in (
                    parameter_node,
                    base,
                    getattr(parameter_node, "inputVolume", None),
                    getattr(parameter_node, "teethSegmentation", None),
                )
            ),
        )

        unknown = (
            str(details.get("acceptanceStatus") or "") == "unknown"
            or bool(details.get("acceptanceUncertainty"))
        )
        visible_status = (
            "Cyan translucent ghost shows the staged candidate; the solid robot may "
            "reflect an uncertain native state."
            if unknown
            else "Cyan translucent ghost shows the staged candidate; the solid robot "
            "shows the accepted Base."
        )
        if getattr(self, "_manualBaseCandidateGhostKey", None) == cache_key:
            return visible_status

        show = getattr(logic, "showManualBaseCandidateGhost", None)
        if not callable(show):
            shown, message = False, "candidate visualization API unavailable"
        else:
            try:
                shown, message = show(candidate)
            except Exception as exc:
                shown, message = False, str(exc)
        if shown:
            self._manualBaseCandidateGhostKey = cache_key
            return visible_status

        clear_ghost()
        reason = str(message or "local robot models are unavailable")
        return (
            f"Candidate visualization unavailable: {reason}. "
            "The staged candidate remains unaccepted."
        )

    def _step6BasePoseEvidence(self, reviewResult=None) -> str:
        ghost_status = self._syncManualBaseCandidateGhost(reviewResult)
        if not self._parameterNode or not self.logic:
            return _("Candidate Base pose is unavailable.") + (
                " " + ghost_status if ghost_status else ""
            )
        base = self._parameterNode.robotBaseTransform
        if not self.logic.isRobotBaseTransformNode(base):
            return _("Candidate Base transform is unavailable.") + (
                " " + ghost_status if ghost_status else ""
            )
        try:
            matrix = vtk.vtkMatrix4x4()
            base.GetMatrixTransformToWorld(matrix)
            values = tuple(
                float(matrix.GetElement(row, column))
                for row in range(3)
                for column in range(4)
            )
            if not all(math.isfinite(value) for value in values):
                return _("Candidate Base pose contains non-finite matrix values.")
            x, y, z = values[3], values[7], values[11]
            rotation = tuple(
                tuple(values[row * 4 + column] for column in range(3))
                for row in range(3)
            )
            rotation_text = "; ".join(
                "(" + ", ".join(f"{value:.5f}" for value in row) + ")"
                for row in rotation
            )
            fingerprint = str(self.logic.robotBasePoseFingerprint(base) or "unavailable")
            accepted_text = (
                "Accepted Base — world RAS origin "
                f"({x:.3f}, {y:.3f}, {z:.3f}) mm; rotation rows "
                f"{rotation_text}; pose fingerprint {fingerprint[:12]}"
            )
            details = getattr(reviewResult, "details", {}) or {}
            staged = bool(details.get("staged"))
            identity_status = str(details.get("identityStatus") or "unknown")
            candidate = details.get("candidateMatrixWorldRasMm")
            candidate_text = "No detached Base candidate is staged."
            if staged:
                try:
                    candidate_values = tuple(float(value) for value in candidate)
                    if len(candidate_values) != 16 or not all(
                        math.isfinite(value) for value in candidate_values
                    ):
                        raise ValueError("invalid 4 x 4 matrix evidence")
                    candidate_x, candidate_y, candidate_z = (
                        candidate_values[3], candidate_values[7], candidate_values[11]
                    )
                    candidate_rows = "; ".join(
                        "(" + ", ".join(
                            f"{candidate_values[row * 4 + col]:.5f}"
                            for col in range(3)
                        ) + ")"
                        for row in range(3)
                    )
                    candidate_text = (
                        "Review candidate — world RAS origin "
                        f"({candidate_x:.3f}, {candidate_y:.3f}, {candidate_z:.3f}) mm; "
                        f"rotation rows {candidate_rows}; identity {identity_status}."
                    )
                except (TypeError, ValueError, OverflowError):
                    candidate_text = (
                        "Review candidate matrix evidence is invalid; preserve the "
                        f"candidate and do not accept it. Identity {identity_status}."
                    )
            elif identity_status != "current":
                candidate_text = (
                    "No detached Base candidate is staged; review identity is "
                    f"{identity_status}."
                )
            acceptance_unknown = (
                str(details.get("acceptanceStatus") or "") == "unknown"
                or bool(details.get("acceptanceUncertainty"))
            )
            state_text = (
                "Native scene state is unverified; Base acceptance is blocked until "
                "runtime reconciliation confirms it."
                if acceptance_unknown
                else "Staging alone leaves the accepted robot model and ROS scene unchanged; "
                "only acknowledged acceptance promotes the candidate."
            )
            review_text = (
                accepted_text + ". " + candidate_text + " Numeric review only. "
                + state_text
            )
            if ghost_status:
                review_text += " " + ghost_status
            failure = details.get("failureEvidence")
            if failure is not None:
                review_text += " Preserved Base acceptance failure evidence: " + str(failure)
            panel = getattr(self, "_robotSimulationPanel", None)
            if panel and hasattr(panel, "manualBaseReviewStatusLabel"):
                panel.manualBaseReviewStatusLabel.text = review_text
                panel.cancelManualBaseReviewButton.enabled = (
                    staged and not acceptance_unknown
                )
            return accepted_text + ". " + candidate_text + (
                " " + ghost_status if ghost_status else ""
            )
        except (AttributeError, OverflowError, RuntimeError, TypeError, ValueError) as exc:
            return _("Candidate Base pose evidence is unavailable: %1").replace(
                "%1", str(exc)
            )

    def _updateStep6PlanningUi(self, message: str = "", error: bool = False) -> None:
        clear_stale_display = getattr(
            self, "_clearStep6MotionDiagnosticDisplayIfContextChanged", None
        )
        if callable(clear_stale_display):
            clear_stale_display()
        if not hasattr(self, "ui") or not self._parameterNode:
            return
        imported = bool(self._parameterNode.step6PlanningContextImported)
        locked = bool(self._parameterNode.robotBaseMountLocked)
        facade_plan = (
            self._robotWorkflowFacade.motionPlan
            if self._robotWorkflowFacade
            else None
        )
        active_plan = facade_plan or self._step6MotionPlan
        has_plan = active_plan is not None and active_plan.success
        scene_kind = self._step6SceneKind()
        stage_entries = self._workflowStageEntries()
        robot_stage_active = bool(
            stage_entries
            and int(self.ui.workflowStageComboBox.currentIndex) == len(stage_entries) - 1
            and not self._isStep3BActive()
        )
        scene_active = scene_kind == "case"
        case_jaw_issues = (
            self.logic.step6CaseJawOpeningFreshnessIssues(self._parameterNode)
            if self.logic and scene_kind == "case"
            else []
        )
        case_placement_issues = (
            self.logic.step6CaseJawPlacementFreshnessIssues(self._parameterNode)
            if self.logic and scene_kind == "case"
            else []
        )
        foundation = (
            self.logic.evaluateCaseFoundationEligibility(self._parameterNode)
            if self.logic and scene_kind == "case"
            else None
        )
        branchEligibility = (
            self.logic.evaluatePreparedBranchEligibility(self._parameterNode)
            if self.logic and scene_kind == "case"
            else None
        )
        scene_prepared = bool(scene_kind == "case" and not case_placement_issues)
        planning_anatomy_ready = bool(scene_kind == "case" and not case_jaw_issues)
        robot_present = self._step6RobotPresent()
        local_robot_present = bool(self.logic.robotModelNodes()) if self.logic else False
        ros2_active = self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        ) if self.logic else False
        home_issues = self.logic.taskHomeFreshnessIssues(self._parameterNode) if self.logic else ()
        home_ready = not home_issues
        home_runtime_validated = bool(
            self._robotWorkflowFacade
            and self._robotWorkflowFacade.taskHomeRuntimeValidated(
                self._parameterNode
            )
        )
        workspace_runtime_validated = bool(
            self._robotWorkflowFacade
            and self._robotWorkflowFacade.workspaceRuntimeValidated(
                self._parameterNode
            )
        )
        assisted_reviewed = (
            self.logic.assistedTaskLimitsReviewed(self._parameterNode)
            if self.logic else False
        )
        task_issues = self.logic.confirmedTaskFreshnessIssues(
            self._parameterNode
        ) if self.logic else ()
        task_ready = not task_issues
        facade_capabilities = (
            self._robotWorkflowFacade.capabilities()
            if self._robotWorkflowFacade else None
        )

        if message:
            context_status = message
        elif scene_kind == "case" and case_jaw_issues:
            context_status = _(
                "Complete Case Foundation — Open Mouth Setup before loading or "
                "placing the robot: %1"
            ).replace("%1", " ".join(case_jaw_issues))
        elif (
            scene_kind == "case"
            and foundation
            and foundation["base"]["eligible"]
            and branchEligibility
            and not branchEligibility["branch"]
        ):
            context_status = _(
                "Case Foundation and reviewed base are ready. Complete Steps "
                "4A–5C before activating a PreparedBranch."
            )
        elif scene_kind == "case":
            context_status = _(
                "Case Foundation planning pose is current."
            )
        else:
            context_status = _("No Case Foundation is loaded yet.")

        base_state = str(self._parameterNode.step6BasePlacementStatus or "Unlocked")
        base_source = str(self._parameterNode.step6BasePlacementSource or "")
        review_result = (
            self._robotWorkflowFacade.manualBaseReview()
            if self._robotWorkflowFacade and robot_stage_active
            else None
        )
        base_pose_evidence = self._step6BasePoseEvidence(review_result)
        review_details = getattr(review_result, "details", {}) or {}
        manual_base_review_staged = bool(review_details.get("staged"))
        manual_base_identity_current = (
            str(review_details.get("identityStatus") or "unknown") == "current"
        )
        manual_base_acceptance_unknown = (
            str(review_details.get("acceptanceStatus") or "") == "unknown"
            or bool(review_details.get("acceptanceUncertainty"))
        )
        if base_state == BasePlacementStatus.STALE.value:
            mount_status = (
                _(
                    "Base review is Stale (%1). Its evidence remains visible, "
                    "and Accept Base is disabled until current identity is restored. %2"
                ).replace("%1", base_source or "unreviewed source")
                .replace("%2", base_pose_evidence)
            )
        elif locked:
            mount_status = _(
                "Accepted Manual Simulation Base — %1. Diagnostic placement only; "
                "no forehead or registration truth. %2"
            ).replace("%1", base_state).replace("%2", base_pose_evidence)
        elif not scene_active:
            mount_status = _("Choose a scene before loading the robot.")
        elif not scene_prepared:
            mount_status = _("Complete Case Foundation — Open Mouth Setup.")
        elif not robot_present:
            mount_status = _("Load the ROS robot (or MRML fallback) before placing.")
        else:
            mount_status = _(
                "Start a numeric Base review, adjust with the local-axis controls, "
                "then choose Accept Base. Only acknowledged acceptance promotes "
                "the candidate. %1"
            ).replace("%1", base_pose_evidence)
        if manual_base_acceptance_unknown:
            mount_status = _(
                "Base acceptance outcome is unknown. Further acceptance is blocked "
                "until runtime reconciliation confirms the native scene state. %1"
            ).replace("%1", base_pose_evidence)

        if message and "motion plan" in message.lower():
            plan_status = message
        elif has_plan:
            plan_status = active_plan.message
        elif not imported:
            plan_status = _("Activate a verified PreparedBranch before planning motion.")
        else:
            plan_status = _("No motion plan yet.")

        style_ok = "color: #207227;"
        style_warn = "color: #b36b00;"
        style_err = "color: #b00020;"
        style = style_err if error else (
            style_ok if scene_active or has_plan else style_warn
        )

        self.ui.step6PlanningContextStatusLabel.text = context_status
        self.ui.step6PlanningContextStatusLabel.styleSheet = (
            style_ok if scene_prepared else style_warn
        )
        self.ui.step6MountLockStatusLabel.text = mount_status
        self.ui.step6MountLockStatusLabel.styleSheet = (
            style_ok
            if locked and base_state != BasePlacementStatus.STALE.value
            else style_warn
        )
        self.ui.step6TrajectoryPlanningStatusLabel.text = plan_status
        self.ui.step6TrajectoryPlanningStatusLabel.styleSheet = (
            style_err if error else (style_ok if has_plan else style_warn)
        )

        self.ui.step6MountLockGroupBox.enabled = scene_prepared
        self.ui.step6TaskJointLimitsGroupBox.enabled = (
            robot_present and scene_prepared and ros2_active
        )
        self.ui.step6WorkspaceGroupBox.enabled = bool(
            robot_present
            and scene_prepared
            and ros2_active
            and home_runtime_validated
        )
        self.ui.step6TrajectoryPlanningGroupBox.enabled = (
            locked and imported and planning_anatomy_ready
        )

        place_enabled = scene_prepared and robot_present and not locked
        self.ui.lockRobotBaseMountButton.enabled = bool(
            scene_prepared
            and robot_present
            and not locked
            and (
                not robot_stage_active
                or (
                    manual_base_review_staged
                    and manual_base_identity_current
                    and not manual_base_acceptance_unknown
                    and bool(getattr(review_result, "success", False))
                )
            )
        )
        self.ui.unlockRobotBaseMountButton.enabled = locked
        self.ui.planTrajectoryMotionButton.enabled = (
            imported and locked and planning_anatomy_ready
        )
        self.ui.previewTrajectoryMotionButton.enabled = False
        self.ui.stopTrajectoryMotionButton.enabled = (
            self._step6MotionPreviewTimer is not None
            or bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.previewActive
            )
        )

        # Retired XML controls remain only while the old UI file is migrated.
        # Runtime ownership is exclusively the shared 6.1 panel; never allow
        # these hidden buttons to become a second state-changing action path.
        self.ui.connectRos2MotionButton.enabled = False
        self.ui.disconnectRos2MotionButton.enabled = False
        robot_recovery_allowed = bool(
            scene_prepared
            and not local_robot_present
            and self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            )
        )
        self.ui.loadRobotModelButton.enabled = bool(
            scene_prepared and (not locked or robot_recovery_allowed)
        )
        self.ui.frameRobotButton.enabled = scene_prepared
        self.ui.importStep6PlanningContextButton.enabled = bool(
            branchEligibility
            and branchEligibility["eligible"]
            and not ros2_active
        )
        self.ui.resetRobotBaseButton.enabled = place_enabled
        for widget_name in (
            "createRobotMountPlaneButton",
            "flipRobotMountPlaneButton",
            "snapRobotBaseToPlaneButton",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setEnabled(False)
        self.ui.robotMountPlaneSelector.enabled = False
        self.ui.robotBaseTransformSelector.enabled = not robot_stage_active
        for widget_name in (
            "robotXMinusButton",
            "robotXPlusButton",
            "robotYMinusButton",
            "robotYPlusButton",
            "robotZMinusButton",
            "robotZPlusButton",
            "robotRxMinusButton",
            "robotRxPlusButton",
            "robotRyMinusButton",
            "robotRyPlusButton",
            "robotRzMinusButton",
            "robotRzPlusButton",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setEnabled(place_enabled)
        self.ui.robotKeyboardNudgeCheckBox.enabled = place_enabled
        self.ui.resetRobotJointsButton.enabled = bool(
            robot_present
            and scene_prepared
            and ros2_active
            and not robot_stage_active
        )
        self.ui.resetRobotJointsButton.toolTip = _(
            "Use the 6.3 Manual Jog draft Reset and Guarded Jog actions to change "
            "joint state during Step 6."
            if robot_stage_active
            else "Reset all joints to the selected zero pose."
        )
        self.ui.deleteRobotSetupButton.enabled = robot_present and not locked
        self.ui.applyTaskJointLimitsButton.enabled = bool(
            robot_present and scene_prepared and ros2_active
        )
        self.ui.resetTaskJointLimitsButton.enabled = bool(
            robot_present and scene_prepared and ros2_active
        )
        self.ui.generateRobotWorkspaceButton.enabled = (
            scene_prepared
            and robot_present
            and locked
            and ros2_active
            and home_runtime_validated
            and self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            )
        )
        self.ui.clearRobotWorkspaceButton.enabled = bool(
            self.logic.robotWorkspaceModelNode()
        )

        panel = self._robotSimulationPanel
        if panel is not None:
            facade = self._robotWorkflowFacade
            try:
                task_home_review_result = (
                    facade.manualTaskHomeReview() if facade else None
                )
            except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
                task_home_review_result = None
            task_home_details = getattr(task_home_review_result, "details", {}) or {}
            if not isinstance(task_home_details, Mapping):
                task_home_details = {}
            offline_home_draft_ready = bool(
                task_home_details.get("setupMode") == "offline"
                and bool(getattr(task_home_review_result, "success", False))
                and str(task_home_details.get("identityStatus") or "") == "current"
                and str(task_home_details.get("acceptanceStatus") or "")
                in {"review", "accepted", "configuration_saved"}
                and not task_home_details.get("acceptanceUncertainty")
                and not getattr(self, "_workflowActionBusy", False)
            )
            task_home_live_scene = bool(
                scene_prepared
                and robot_present
                and locked
                and ros2_active
                and not self._workflowActionBusy
                and not getattr(self, "_step6MotionPreviewTimer", None)
                and not bool(getattr(facade, "previewActive", False))
                and not bool(getattr(facade, "returnHomeRequired", False))
            )
            task_home_controls = self._manualTaskHomeReviewControlState(
                task_home_live_scene, task_home_review_result
            )
            panel.homeGroup.enabled = bool(
                task_home_controls["group"]
                or scene_prepared
                or task_home_controls["cancel"]
            )
            panel.reviewTaskHomeButton.enabled = bool(
                task_home_controls["review"] and not self._workflowActionBusy
            )
            panel.cancelTaskHomeReviewButton.enabled = bool(
                task_home_controls["cancel"] and not self._workflowActionBusy
            )
            panel.acceptTaskHomeButton.enabled = bool(
                task_home_controls["accept"] and not self._workflowActionBusy
            )
            panel.reconcileTaskHomeButton.enabled = bool(
                task_home_controls["reconcile"] and not self._workflowActionBusy
            )
            panel.setManualTaskHomeReviewResult(task_home_review_result)
            if robot_stage_active:
                control_state = self._manualBaseReviewControlState(
                    scene_prepared, robot_present, locked, review_result, ros2_active
                )
                panel.manualBaseReviewGroup.enabled = control_state["group"]
                panel.beginManualBaseReviewButton.enabled = control_state["begin"]
                panel.cancelManualBaseReviewButton.enabled = control_state["cancel"]
                panel.reconcileManualBaseStateButton.enabled = bool(
                    control_state["reconcile"] and not self._workflowActionBusy
                )
                reconcile_base = bool(
                    control_state["reconcile"] and not self._workflowActionBusy
                )
                self.ui.lockRobotBaseMountButton.text = _(
                    "Reconcile Base State" if reconcile_base else "Accept Base"
                )
                self.ui.lockRobotBaseMountButton.toolTip = _(
                    "Reconcile the accepted Base with the live ROS scene. This does not "
                    "accept the detached candidate."
                    if reconcile_base
                    else "Accept the detached numeric Base candidate through the guarded "
                    "Step 6 Base review path. An unknown lock/scene outcome blocks later "
                    "acceptance until runtime reconciliation."
                )
                self.ui.lockRobotBaseMountButton.enabled = bool(
                    (control_state["accept"] or reconcile_base)
                    and not self._workflowActionBusy
                )
            else:
                panel.manualBaseReviewGroup.enabled = False
                self.ui.lockRobotBaseMountButton.text = _("Accept Base")
            try:
                urdf_path, _package_root = self.logic.robotDescriptionPaths()
                mechanical_limits = default_task_joint_limits_from_urdf(urdf_path)
                reviewed_limits = (
                    mechanical_limits
                    if panel._taskHomeSetupMode == "offline"
                    else build_task_joint_limits_from_parameter_values(
                        j1_min=self._parameterNode.robotJoint1TaskMinDeg,
                        j1_max=self._parameterNode.robotJoint1TaskMaxDeg,
                        j2_min=self._parameterNode.robotJoint2TaskMinMm,
                        j2_max=self._parameterNode.robotJoint2TaskMaxMm,
                        j3_min=self._parameterNode.robotJoint3TaskMinDeg,
                        j3_max=self._parameterNode.robotJoint3TaskMaxDeg,
                        j4_min=self._parameterNode.robotJoint4TaskMinMm,
                        j4_max=self._parameterNode.robotJoint4TaskMaxMm,
                        j5_min=self._parameterNode.robotJoint5TaskMinDeg,
                        j5_max=self._parameterNode.robotJoint5TaskMaxDeg,
                    )
                )
                panel.setManualJogLimits(mechanical_limits, reviewed_limits)
                if panel._taskHomeSetupMode == "offline":
                    try:
                        robot_joint_positions = self._robotJointPositionsSi()
                    except (AttributeError, RuntimeError, TypeError, ValueError):
                        robot_joint_positions = {}
                    panel.setManualJogLocalJointPositions(robot_joint_positions)
                elif panel._taskHomeSetupMode == "connected":
                    panel.setManualJogAcceptedState(self._robotJointPositionsSi())
            except (OSError, RuntimeError, TypeError, ValueError) as exc:
                panel.setManualJogLimitsUnavailable(str(exc))
            panel.loadFallbackButton.enabled = bool(
                scene_prepared and (not locked or robot_recovery_allowed)
            )
            panel.enableCbctRenderingButton.enabled = imported and scene_prepared
            panel.createProxyButton.enabled = bool(
                scene_prepared and not ros2_active
            )
            panel.motionDiagnosticsButton.enabled = bool(
                str(self._parameterNode.step6MotionDiagnosticJson or "").strip()
            )
            panel.showPlannerComparisonButton.enabled = bool(
                str(self._parameterNode.step6PlannerComparisonJson or "").strip()
            )
            panel.applyTaskHomeButton.enabled = bool(
                scene_prepared and ros2_active and home_ready
            )
            if panel._taskHomeSetupMode == "offline":
                if panel._taskHomeConfigurationReady:
                    panel.homeStatusLabel.text = _(
                        "Saved Home configuration is offline only and is not a live-validated robot pose. "
                        "Connect ROS + MoveIt in 6.1, then return to 6.2 to accept and validate it."
                    )
                else:
                    panel.homeStatusLabel.text = _(
                        "Offline setup: edit and save a mechanically bounded Home configuration here. "
                        "Connect ROS + MoveIt in 6.1 to validate it as a live Task Home."
                    )
            elif home_runtime_validated:
                panel.homeStatusLabel.text = _(
                    "Accepted Task Home is current and live-validated in this ROS/MoveIt session."
                )
            elif home_ready and ros2_active:
                panel.homeStatusLabel.text = _(
                    "Saved Task Home is current but unvalidated. Review and accept it in 6.2 to validate this runtime; Plan + Apply is a separate operation."
                )
            elif home_ready:
                panel.homeStatusLabel.text = _(
                    "Saved Task Home is current; connect ROS/MoveIt in 6.1 to validate it."
                )
            else:
                panel.homeStatusLabel.text = (
                    "Saved Task Home status: " + " ".join(home_issues)
                )
            panel.reviewLimitsButton.enabled = bool(
                scene_prepared
                and ros2_active
                and home_runtime_validated
                and workspace_runtime_validated
                and str(self._parameterNode.step6AssistedLimitProposalJson or "").strip()
                and not assisted_reviewed
            )
            panel.revalidateWorkspaceButton.enabled = bool(
                scene_prepared
                and ros2_active
                and home_runtime_validated
                and not workspace_runtime_validated
                and str(
                    self._parameterNode.step6AssistedLimitProposalJson or ""
                ).strip()
            )
            if workspace_runtime_validated and assisted_reviewed:
                panel.workspaceReviewStatusLabel.text = _(
                    "MoveIt static-valid workspace and bounded Home-connectivity "
                    "evidence are current; its assisted envelope was explicitly reviewed."
                )
            elif workspace_runtime_validated:
                panel.workspaceReviewStatusLabel.text = _(
                    "MoveIt static-valid workspace and bounded Home-connectivity "
                    "evidence are current; review its proposed envelope."
                )
            elif str(
                self._parameterNode.step6AssistedLimitProposalJson or ""
            ).strip():
                panel.workspaceReviewStatusLabel.text = _(
                    "Saved workspace evidence needs live revalidation. Replay it "
                    "without changing the reviewed envelope, or regenerate it "
                    "if replay rejects any state."
                )
            else:
                panel.workspaceReviewStatusLabel.text = _(
                    "Generate the MoveIt static-valid workspace and bounded "
                    "Home-connectivity evidence, then review its proposed limits."
                )
            runtime_ready = bool(
                planning_anatomy_ready
                and local_robot_present
                and locked
                and imported
                and foundation
                and foundation["base"]["eligible"]
                and branchEligibility
                and branchEligibility["eligible"]
            )
            panel.connectButton.enabled = runtime_ready and not ros2_active
            panel.disconnectButton.enabled = ros2_active
            panel.confirmTaskButton.enabled = bool(
                imported
                and planning_anatomy_ready
                and ros2_active
                and home_runtime_validated
                and facade_capabilities
                and facade_capabilities.planning_scene_synchronized
            )
            confirmation_prerequisites = []
            if not imported:
                confirmation_prerequisites.append(_("Activate the verified PreparedBranch in 6.0."))
            if not planning_anatomy_ready:
                confirmation_prerequisites.append(_("Refresh the Case Foundation planning anatomy."))
            if not ros2_active:
                confirmation_prerequisites.append(_("Connect ROS + MoveIt in 6.1."))
            if not home_runtime_validated:
                confirmation_prerequisites.append(_("Apply and live-validate Task Home in 6.2."))
            if not facade_capabilities or not facade_capabilities.planning_scene_synchronized:
                confirmation_prerequisites.append(_("Complete the authoritative planning-scene audit in 6.1."))
            planning_prerequisites = list(confirmation_prerequisites)
            if not workspace_runtime_validated:
                planning_prerequisites.append(
                    _("Revalidate or generate workspace evidence in 6.3.")
                )
            if not assisted_reviewed:
                planning_prerequisites.append(
                    _("Review and apply assisted joint limits in 6.3.")
                )
            panel.confirmationStatusLabel.text = (
                _("Immutable task snapshot is current; phased plans are enabled.")
                if task_ready and workspace_runtime_validated and assisted_reviewed
                else " ".join(planning_prerequisites or task_issues)
            )
            preview_active = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.previewActive
            )
            away_from_home = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.returnHomeRequired
            )
            panel.setManualJogAvailability(
                draft_available=bool(
                    (ros2_active and local_robot_present)
                    or offline_home_draft_ready
                ),
                jog_available=bool(
                    planning_anatomy_ready
                    and ros2_active
                    and facade_capabilities
                    and facade_capabilities.planning_scene_synchronized
                    and self._manualJogIdentityCurrent()
                    and not preview_active
                    and not away_from_home
                    and not getattr(self, "_workflowActionBusy", False)
                ),
            )
            if panel._taskHomeSetupMode == "offline":
                offline_edit_ready = bool(
                    offline_home_draft_ready and panel._manualJogAvailable
                )
                panel.reviewTaskHomeButton.enabled = bool(
                    task_home_controls["review"]
                    and offline_edit_ready
                    and not self._workflowActionBusy
                )
                panel.acceptTaskHomeButton.enabled = bool(
                    task_home_controls["accept"]
                    and offline_edit_ready
                    and not self._workflowActionBusy
                )
            phase_planning_ready = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and home_runtime_validated
                and workspace_runtime_validated
                and assisted_reviewed
                and not away_from_home
                and not getattr(self, "_plannerComparisonState", None)
            )
            panel.planApproachButton.enabled = phase_planning_ready
            panel.checkPreEntryIKButton.enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and home_runtime_validated
                and facade_capabilities
                and facade_capabilities.planning_scene_synchronized
                and not preview_active
                and not away_from_home
                and not getattr(self, "_plannerComparisonState", None)
            )
            stage_diagnostic_enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and home_runtime_validated
                and facade_capabilities
                and facade_capabilities.planning_scene_synchronized
                and not preview_active
                and not away_from_home
                and not getattr(self, "_plannerComparisonState", None)
            )
            for button in (
                panel.checkPlanningP1Button,
                panel.checkPlanningP2Button,
                panel.checkPlanningP3Button,
            ):
                button.enabled = stage_diagnostic_enabled
            panel.comparePlannersButton.enabled = phase_planning_ready
            override_active = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.templateCollisionExclusionActive
            )
            panel.templateCollisionOverrideCheckBox.blockSignals(True)
            panel.templateCollisionOverrideCheckBox.checked = override_active
            panel.templateCollisionOverrideCheckBox.blockSignals(False)
            panel.templateCollisionOverrideCheckBox.enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and not preview_active
                and not away_from_home
                and self._parameterNode.finalPrintableTemplateModel is not None
                and os.environ.get(
                    "DENTOBOT_ENABLE_HISTORICAL_TEMPLATE_OVERRIDE", ""
                )
                == "1"
            )
            panel.templateCollisionOverrideStatusLabel.text = (
                _(
                    "ACTIVE — FUNCTIONAL SIMULATION ONLY. The unresolved Step 5C "
                    "final template stays visible but is excluded from MoveIt; "
                    "results are not physical collision-valid evidence."
                )
                if override_active
                else _(
                    "Retired — the complete Step 5C template remains collision checked."
                )
            )
            self._refreshStep6AnatomyReviewControls()
            anatomy_review_active = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.anatomyReviewState.get("active")
            )
            panel.anatomyReviewGroup.enabled = bool(
                not preview_active
                and not away_from_home
                and (
                    (self._robotWorkflowFacade and self._robotWorkflowFacade.anatomyReviewState.get("exists"))
                    or (planning_anatomy_ready and ros2_active and os.environ.get(
                        "DENTOBOT_ENABLE_HISTORICAL_ANATOMY_REVIEW", ""
                    ) == "1")
                )
            )
            if anatomy_review_active:
                panel.planApproachButton.toolTip = _(
                    "Research simulation anatomy override is active. The source "
                    "segmentation remains unchanged; results are not physical "
                    "collision-valid evidence."
                )
            else:
                panel.planApproachButton.toolTip = ""
            drilling_preflight_ready = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.drillingPreflightReady
            )
            panel.previewApproachButton.enabled = bool(
                drilling_preflight_ready
                and isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.APPROACH.value
                and task_ready
                and ros2_active
                and not preview_active
                and not away_from_home
            )
            panel.stopPreviewButton.enabled = preview_active
            panel.returnHomeButton.enabled = bool(
                ros2_active and away_from_home and not preview_active
            )
            approach_complete = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.completedPhase == MotionPhase.APPROACH.value
            )
            panel.planDrillingButton.enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and approach_complete
                and drilling_preflight_ready
                and not preview_active
            )
            panel.previewDrillingButton.enabled = bool(
                drilling_preflight_ready
                and approach_complete
                and isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.DRILLING.value
                and task_ready
                and ros2_active
                and not preview_active
                and not away_from_home
            )
            if not drilling_preflight_ready:
                panel.drillingStatusLabel.text = _(
                    "Drill preview is blocked until Approach planning returns a complete guarded "
                    "Stage 3 preflight. Inspect partial Stage 3 evidence and paths "
                    "in Planning & Diagnostics; partial output cannot unlock drilling."
                )
            elif not approach_complete:
                panel.drillingStatusLabel.text = _(
                    "The complete Stage 3 preflight is retained. Preview Approach "
                    "through Entry before creating the Drill preview."
                )

    def _applyTaskJointLimitsToJointSpinboxes(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        pairs = (
            (self.ui.robotJoint1SpinBox, "joint_1"),
            (self.ui.robotJoint2SpinBox, "joint_2"),
            (self.ui.robotJoint3SpinBox, "joint_3"),
            (self.ui.robotJoint4SpinBox, "joint_4"),
            (self.ui.robotJoint5SpinBox, "joint_5"),
        )
        if self._isStep6RobotWorkflowActive():
            urdf_path, _package_root = self.logic.robotDescriptionPaths()
            mechanical_limits = default_task_joint_limits_from_urdf(urdf_path)
            for spinbox, joint_name in pairs:
                joint_limit = getattr(mechanical_limits, joint_name)
                previously_blocked = spinbox.blockSignals(True)
                try:
                    spinbox.setRange(joint_limit.minimum, joint_limit.maximum)
                    spinbox.setReadOnly(True)
                finally:
                    spinbox.blockSignals(previously_blocked)
            return

        for spinbox, _joint_name in pairs:
            spinbox.setReadOnly(False)
        limits = self.logic.getTaskJointLimits(self._parameterNode)
        reviewed_pairs = (
            limits.joint_1,
            limits.joint_2,
            limits.joint_3,
            limits.joint_4,
            limits.joint_5,
        )
        for (spinbox, _joint_name), joint_limit in zip(
            pairs, reviewed_pairs, strict=True
        ):
            minimum, maximum, value = apply_task_limit_range_to_value(
                spinbox.value,
                joint_limit,
            )
            spinbox.setMinimum(minimum)
            spinbox.setMaximum(maximum)
            spinbox.setValue(value)
    def _onTaskJointLimitSpinBoxChanged(self, value: float = 0.0) -> None:
        del value
        if (
            self._updatingFromParameterNode
            or self._updatingRobotPlacementUI
            or (
                self._robotWorkflowFacade is not None
                and self._robotWorkflowFacade.displaySyncActive
            )
        ):
            return
        try:
            if self.logic and self._parameterNode:
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Task joint limits changed."),
                )
            self._step6MotionPlan = None
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.invalidateWorkspaceRuntimeValidation()
            self._applyTaskJointLimitsToJointSpinboxes()
            if self.logic.deleteRobotWorkspaceModel():
                self.ui.robotWorkspaceStatusLabel.text = _(
                    "Task limits changed. Generate a new workspace cloud."
                )
                self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
        except ValueError:
            pass

    def _setRobotJointsFromSi(
        self,
        joint_positions_si: dict[str, float],
        *,
        publish_to_ros: bool = True,
    ) -> tuple[bool, str]:
        if not self._parameterNode:
            return False, _("Step 6 parameter node is unavailable.")
        was_modifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotJoint1Deg = degrees(
                joint_positions_si["link-1_Revolute-1"],
            )
            self._parameterNode.robotJoint2Mm = (
                joint_positions_si["link-2_Slider-2"] * 1000.0
            )
            self._parameterNode.robotJoint3Deg = degrees(
                joint_positions_si["link-3_Revolute-3"],
            )
            self._parameterNode.robotJoint4Mm = (
                joint_positions_si["link-4_Slider-4"] * 1000.0
            )
            self._parameterNode.robotJoint5Deg = degrees(
                joint_positions_si["link-5_Revolute-5"],
            )
        finally:
            self._parameterNode.EndModify(was_modifying)
        self._updateRobotPlacement()
        if (
            publish_to_ros
            and self.logic
            and self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
        ):
            ok, message = apply_joint_positions_si_to_motion_control(joint_positions_si)
            if not ok:
                return False, message
        return True, ""

    def onImportStep6PlanningContext(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if self._caseBundleRobotProfileCompatible is False:
                raise ValueError(
                    _(
                        "The installed URDF/SRDF/mesh/MoveIt resources do not "
                        "match this case package. Reconcile the robot profile "
                        "before importing the case into Step 6."
                    )
                )
            if not self._confirmStep6SceneSwitch("case"):
                return
            report = self.logic.importStep6PlanningContext(self._parameterNode)
            try:
                self._applyTaskJointLimitsToJointSpinboxes()
            except ValueError:
                pass
            self._applyStep6RecommendedView()
            self.onFrameStep6CaseScene()
            self._updateStep6PlanningUi(report.message)
        except (RuntimeError, ValueError) as exc:
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onLockRobotBaseMount(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        if self._isStep6RobotWorkflowActive():
            if not self._isStep6ManualBaseReviewActive():
                return
            panel = getattr(self, "_robotSimulationPanel", None)
            if panel and panel.reconcileManualBaseStateButton.enabled:
                self._onStep6ReconcileManualBaseAcceptance()
                return
            result = self._robotWorkflowFacade.acceptManualBaseReview()
            self._updateStep6PlanningUi(result.message, error=not result.success)
            if result.success:
                self._updateRobotPlacement()
            else:
                slicer.util.errorDisplay(result.message)
            return
        result = self._robotWorkflowFacade.lockBase()
        if result.success:
            try:
                self._captureCaseFoundationSessionSnapshot()
            except Exception:
                logging.exception(
                    "Case Foundation session snapshot failed after locking the robot base"
                )
            if self._isStep3BActive():
                self._updateRobotPlacement()
                self._applyStep3BRecommendedView()
                self._ensureOfflinePlacementSceneVisible()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def onUnlockRobotBaseMount(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        if (
            self._isStep6RobotWorkflowActive()
            and not self._isStep6ManualBaseReviewActive()
        ):
            return
        result = self._robotWorkflowFacade.unlockBase()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def onApplyTaskJointLimits(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self._applyTaskJointLimitsToJointSpinboxes()
            self._updateStep6PlanningUi(_("Task joint limits applied to Step 6 controls."))
        except ValueError as exc:
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetTaskJointLimits(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        self.logic.resetTaskJointLimitsToUrdf(self._parameterNode)
        self._applyTaskJointLimitsToJointSpinboxes()
        self._updateStep6PlanningUi(_("Task joint limits reset to URDF mechanical bounds."))

    def onGenerateRobotWorkspace(self, checked: bool = False) -> None:
        """Build a deterministic, filtered provisional-TCP reach cloud."""
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        if getattr(self, "_workflowActionBusy", False):
            return
        self._workflowActionBusy = True
        progress = None
        workspace_status = ""
        planning_message = ""
        planning_error = False
        try:
            roi_draft = self._step6TaskSpaceRoiDraft()
            if roi_draft is None:
                raise RuntimeError(
                    self._robotSimulationPanel.taskSpaceRoiStatusLabel.text
                    if self._robotSimulationPanel
                    else "Task-space ROI draft is unavailable."
                )
            roi, roi_source = roi_draft
            progress = WorkflowProgress(
                "Step 6 Planning & Diagnostics — TCP workspace"
            )
            progress.update("Checking prerequisites", can_cancel=False)
            result = self._robotWorkflowFacade.generateWorkspaceCloud(
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                ),
                roi=roi,
                roi_source=roi_source,
            )
            workspace_status = result.message
            counts = result.details.get("candidateCounts", {})
            if isinstance(counts, dict):
                count_summary = []
                if "roiCandidateCount" in counts:
                    count_summary.append(
                        f"ROI candidates: {counts['roiCandidateCount']}"
                    )
                for label, success_key, attempt_key, rejected_key in (
                    (
                        "Position-axis IK",
                        "positionAxisIkSuccessCount",
                        "positionAxisIkAttemptCount",
                        "positionAxisIkFailureCount",
                    ),
                    (
                        "MoveIt static validity",
                        "moveItStaticValidityAcceptedCount",
                        "moveItStaticValidityAttemptCount",
                        "moveItStaticValidityRejectedCount",
                    ),
                    (
                        "Task Home connectivity",
                        "homeConnectedCount",
                        "homeConnectivityEvaluatedCount",
                        "homeConnectivityRejectedCount",
                    ),
                ):
                    success = counts.get(success_key)
                    attempted = counts.get(attempt_key)
                    rejected = counts.get(rejected_key)
                    if success is not None and attempted is not None:
                        count_summary.append(
                            f"{label}: {success}/{attempted} passed"
                            + (f", {rejected} rejected" if rejected is not None else "")
                        )
                if count_summary:
                    workspace_status += " Counts: " + "; ".join(count_summary) + "."
            elapsed_sec = result.details.get("elapsedSec")
            if isinstance(elapsed_sec, (int, float)):
                workspace_status += f" Elapsed: {elapsed_sec:.2f} s."
            if not result.success:
                raise RuntimeError(workspace_status)
            self.ui.robotWorkspaceStatusLabel.text = workspace_status + " " + _(
                "Sample counts are diagnostic evidence; they are not a full-route "
                "or independent-guard verdict."
            )
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #207227;"
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.text = (
                "Workspace generation complete: " + workspace_status + " " + _(
                    "Diagnostic samples only; no full-route or independent-guard "
                    "verdict was produced."
                )
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.setProperty(
                "dentobotState", "ok"
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().unpolish(
                self._robotSimulationPanel.taskSpaceRoiStatusLabel
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().polish(
                self._robotSimulationPanel.taskSpaceRoiStatusLabel
            )
            self.ui.clearRobotWorkspaceButton.enabled = True
            planning_message = workspace_status
        except (RuntimeError, ValueError) as exc:
            planning_message = str(exc)
            planning_error = True
            self.ui.robotWorkspaceStatusLabel.text = str(exc)
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b00020;"
            if self._robotSimulationPanel:
                self._robotSimulationPanel.taskSpaceRoiStatusLabel.text = str(exc)
                self._robotSimulationPanel.taskSpaceRoiStatusLabel.setProperty(
                    "dentobotState", "error"
                )
                self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().unpolish(
                    self._robotSimulationPanel.taskSpaceRoiStatusLabel
                )
                self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().polish(
                    self._robotSimulationPanel.taskSpaceRoiStatusLabel
                )
            slicer.util.errorDisplay(str(exc))
        finally:
            try:
                if progress:
                    progress.close()
            finally:
                self._workflowActionBusy = False
                self._updateStep6PlanningUi(planning_message, error=planning_error)

    def onClearRobotWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        self.logic.deleteRobotWorkspaceModel()
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.invalidateWorkspaceRuntimeValidation(
                invalidate_motion_plan=False
            )
        self.ui.robotWorkspaceStatusLabel.text = _("No workspace cloud generated.")
        self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
        if self._robotSimulationPanel:
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.text = _(
                "Workspace cloud cleared; the editable ROI draft and source are retained. "
                "Samples are not generated or validated."
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.setProperty(
                "dentobotState", "blocked"
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().unpolish(
                self._robotSimulationPanel.taskSpaceRoiStatusLabel
            )
            self._robotSimulationPanel.taskSpaceRoiStatusLabel.style().polish(
                self._robotSimulationPanel.taskSpaceRoiStatusLabel
            )
        self.ui.clearRobotWorkspaceButton.enabled = False
        self._updateStep6PlanningUi(_("Workspace evidence was cleared."))

    def onPlanTrajectoryMotion(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        self.onStopTrajectoryMotion()
        action = self._robotWorkflowFacade.planAlongTrajectory()
        self._step6MotionPlan = action.payload if action.success else None
        if not action.success:
            self._step6MotionPlan = None
            self._updateStep6PlanningUi(action.message, error=True)
            slicer.util.errorDisplay(action.message)
            return
        self._updateStep6PlanningUi(action.message)

    def _advanceStep6MotionPreview(self) -> None:
        if not self._step6MotionPlan or not self._step6MotionPlan.waypoint_joint_vectors_si:
            self.onStopTrajectoryMotion()
            return
        waypoints = self._step6MotionPlan.waypoint_joint_vectors_si
        if self._step6MotionPreviewIndex >= len(waypoints):
            self.onStopTrajectoryMotion()
            self._updateStep6PlanningUi(_("Simulated motion preview complete."))
            return
        ok, message = self._setRobotJointsFromSi(
            waypoints[self._step6MotionPreviewIndex]
        )
        if not ok:
            self.onStopTrajectoryMotion()
            self._updateStep6PlanningUi(message, error=True)
            slicer.util.errorDisplay(message)
            return
        self._step6MotionPreviewIndex += 1
        slicer.app.processEvents()

    def onStopTrajectoryMotion(self, checked: bool = False) -> None:
        del checked
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.stopPreview()
        if self._step6MotionPreviewTimer is not None:
            self._step6MotionPreviewTimer.stop()
            self._step6MotionPreviewTimer = None
        self._step6MotionPreviewIndex = 0
        self._updateStep6PlanningUi()
