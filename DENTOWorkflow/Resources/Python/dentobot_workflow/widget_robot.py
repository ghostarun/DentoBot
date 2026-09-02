"""Extracted Step 6 and robot UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


from dentobot_workflow.widget_robot_shell import RobotShellWidgetMixin


from dentobot_workflow.widget_robot_placement import RobotPlacementWidgetMixin


from dentobot_workflow.widget_robot_scene import RobotSceneWidgetMixin


class RobotWidgetMixin(RobotSceneWidgetMixin, RobotPlacementWidgetMixin, RobotShellWidgetMixin):



















































































    def _step6SceneKind(self) -> str:
        if not self._parameterNode or not self.logic:
            return "none"
        imported = bool(self._parameterNode.step6PlanningContextImported)
        phantom = bool(self.logic.draftPhantomModelNodes())
        if imported and phantom:
            return "conflict"
        if imported:
            return "case"
        if phantom:
            return "phantom"
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
        if (
            not stage_entries
            or int(self.ui.workflowStageComboBox.currentIndex)
            != len(stage_entries) - 1
        ):
            return
        if self._step6SceneKind() == "case":
            self._showStep6CaseVolumeInSliceViewers()
        self._applyWorkflowViewPreset("recommended", updateStatus=False)
        self._updateWorkflowViewControls()

    def _confirmStep6SceneSwitch(self, target: str) -> bool:
        kind = self._step6SceneKind()
        if kind in {"none", target}:
            return True
        if target == "case":
            return slicer.util.confirmYesNoDisplay(
                _(
                    "A draft phantom is already loaded. Switch to the case package "
                    "and delete the phantom from the scene?"
                )
            )
        return slicer.util.confirmYesNoDisplay(
            _(
                "A case package is already imported. Switch to the phantom test "
                "scene? Case nodes stay in the scene but the recommended view "
                "will hide them."
            )
        )

    def _updateStep6PlanningUi(self, message: str = "", error: bool = False) -> None:
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
        scene_active = scene_kind in {"case", "phantom"}
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
        scene_prepared = bool(
            scene_kind == "phantom"
            or (scene_kind == "case" and not case_placement_issues)
        )
        planning_anatomy_ready = bool(
            scene_kind == "phantom"
            or (scene_kind == "case" and not case_jaw_issues)
        )
        placement_only_fallback = bool(
            scene_kind == "case"
            and str(self._parameterNode.step6CaseJawPreparationMode)
            == "TargetJawFallback"
            and scene_prepared
        )
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
        elif placement_only_fallback:
            context_status = _(
                "Target-jaw-only fallback is active in unchanged source RAS. "
                "Placement, Task Home, and workspace exploration are enabled; "
                "ROS/collision/task planning remain blocked."
            )
        elif scene_kind == "case" and case_jaw_issues:
            context_status = _(
                "Case package imported. Complete 6.0A before loading or placing "
                "the robot: %1"
            ).replace("%1", " ".join(case_jaw_issues))
        elif scene_kind == "case":
            context_status = _(
                "Case package and opened-mouth planning anatomy are current."
            )
        elif scene_kind == "phantom":
            context_status = _("Draft phantom is the active Step 6 scene.")
        elif scene_kind == "conflict":
            context_status = _(
                "Both a case package and a phantom are present. Choose one scene."
            )
        else:
            context_status = _("No Step 6 scene yet. Import a case or load the phantom.")

        base_state = str(self._parameterNode.step6BasePlacementStatus or "Unlocked")
        base_source = str(self._parameterNode.step6BasePlacementSource or "")
        if locked:
            mount_status = _(
                "Manual Simulation Base: %1 (diagnostic placement only; no "
                "forehead/registration truth)."
            ).replace(
                "%1", base_state
            )
        elif base_state == BasePlacementStatus.STALE.value:
            mount_status = (
                _(
                    "Base placement is Stale (%1). Reposition it directly in "
                    "Robot + CBCT context, then review and lock it again."
                ).replace("%1", base_source or "unreviewed source")
            )
        elif not scene_active:
            mount_status = _("Choose a scene before loading the robot.")
        elif not scene_prepared:
            mount_status = _("Complete the required case mouth opening in 6.0A.")
        elif placement_only_fallback and not robot_present:
            mount_status = _("Load the robot for target-jaw placement testing.")
        elif not robot_present:
            mount_status = _("Load the ROS robot (or MRML fallback) before placing.")
        else:
            mount_status = _(
                "Manual Simulation Base is unlocked; position it directly in "
                "Robot + CBCT context."
            )

        if message and "motion plan" in message.lower():
            plan_status = message
        elif has_plan:
            plan_status = active_plan.message
        elif not imported:
            plan_status = _(
                "Trajectory planning needs the case package. Phantom mode is "
                "for placement testing only."
            )
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
            style_err if scene_kind == "conflict" else (
                style_ok if scene_prepared else style_warn
            )
        )
        self.ui.step6MountLockStatusLabel.text = mount_status
        self.ui.step6MountLockStatusLabel.styleSheet = (
            style_ok if locked else style_warn
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
        self.ui.lockRobotBaseMountButton.enabled = (
            scene_prepared and robot_present and not locked
        )
        self.ui.unlockRobotBaseMountButton.enabled = locked
        self.ui.planTrajectoryMotionButton.enabled = (
            imported and locked and planning_anatomy_ready
        )
        self.ui.previewTrajectoryMotionButton.enabled = has_plan
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
        self.ui.importStep6PlanningContextButton.enabled = not locked
        self.ui.loadDraftPhantomButton.enabled = not locked

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
            robot_present and scene_prepared and ros2_active
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
            panel.loadFallbackButton.enabled = bool(
                scene_prepared and (not locked or robot_recovery_allowed)
            )
            panel.enableCbctRenderingButton.enabled = imported and scene_prepared
            panel.createProxyButton.enabled = False
            panel.saveTaskHomeButton.enabled = bool(
                scene_prepared and locked and ros2_active
            )
            panel.motionDiagnosticsButton.enabled = bool(
                str(self._parameterNode.step6MotionDiagnosticJson or "").strip()
            )
            panel.applyTaskHomeButton.enabled = bool(
                scene_prepared and ros2_active and home_ready
            )
            if home_runtime_validated:
                panel.homeStatusLabel.text = _(
                    "Task Home is current and live-validated in this ROS/MoveIt session."
                )
            elif home_ready and ros2_active:
                panel.homeStatusLabel.text = _(
                    "Saved Task Home is current but unvalidated in this runtime. Apply it now."
                )
            elif home_ready:
                panel.homeStatusLabel.text = _(
                    "Saved Task Home is current; connect ROS/MoveIt in 6.1 to validate it."
                )
            else:
                panel.homeStatusLabel.text = " ".join(home_issues)
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
                    "without changing the reviewed envelope, or regenerate 6.3 "
                    "if replay rejects any state."
                )
            else:
                panel.workspaceReviewStatusLabel.text = _(
                    "Generate the MoveIt static-valid workspace and bounded "
                    "Home-connectivity evidence, then review its proposed limits."
                )
            runtime_ready = bool(
                planning_anatomy_ready and local_robot_present and locked
            )
            panel.connectButton.enabled = runtime_ready and not ros2_active
            panel.disconnectButton.enabled = ros2_active
            panel.confirmTaskButton.enabled = bool(
                imported
                and planning_anatomy_ready
                and ros2_active
                and home_runtime_validated
                and workspace_runtime_validated
                and assisted_reviewed
                and facade_capabilities
                and facade_capabilities.planning_scene_synchronized
            )
            panel.confirmationStatusLabel.text = (
                _("Immutable task snapshot is current; phased plans are enabled.")
                if task_ready
                else " ".join(task_issues)
            )
            panel.planApproachButton.enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and home_runtime_validated
                and workspace_runtime_validated
            )
            panel.previewApproachButton.enabled = bool(
                isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.APPROACH.value
            )
            approach_complete = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.completedPhase == MotionPhase.APPROACH.value
            )
            drilling_preflight_ready = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.drillingPreflightReady
            )
            panel.planDrillingButton.enabled = bool(
                planning_anatomy_ready
                and task_ready
                and ros2_active
                and workspace_runtime_validated
                and approach_complete
                and drilling_preflight_ready
            )
            panel.previewDrillingButton.enabled = bool(
                approach_complete
                and isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.DRILLING.value
            )
            if not drilling_preflight_ready:
                panel.drillingStatusLabel.text = _(
                    "Goal 2 is blocked until Goal 1 returns a complete guarded "
                    "Stage 3 preflight. Inspect partial Stage 3 evidence and paths "
                    "in the 6.5 diagnostics; partial output cannot unlock drilling."
                )
            elif not approach_complete:
                panel.drillingStatusLabel.text = _(
                    "The complete Stage 3 preflight is retained. Preview Goal 1 "
                    "through Entry before creating the Goal 2 drilling preview."
                )

    def _applyTaskJointLimitsToJointSpinboxes(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        limits = self.logic.getTaskJointLimits(self._parameterNode)
        pairs = (
            (self.ui.robotJoint1SpinBox, limits.joint_1),
            (self.ui.robotJoint2SpinBox, limits.joint_2),
            (self.ui.robotJoint3SpinBox, limits.joint_3),
            (self.ui.robotJoint4SpinBox, limits.joint_4),
            (self.ui.robotJoint5SpinBox, limits.joint_5),
            (self.ui.robotJoint6SpinBox, limits.joint_6),
        )
        for spinbox, joint_limit in pairs:
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
            self._parameterNode.robotJoint6Deg = degrees(
                joint_positions_si["pneumatic_spindle-Copy_Revolute-6"],
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
            if self.logic.draftPhantomModelNodes():
                self.logic.deleteDraftPhantom(
                    self._parameterNode.draftJawLandmarks,
                    self._parameterNode.draftJawTransform,
                    self._parameterNode.draftJawGapLine,
                )
                was_modifying = self._parameterNode.StartModify()
                try:
                    self._parameterNode.draftPhantomSkullModel = None
                    self._parameterNode.draftPhantomMandibleModel = None
                    self._parameterNode.draftJawLandmarks = None
                    self._parameterNode.draftJawTransform = None
                    self._parameterNode.draftJawGapLine = None
                finally:
                    self._parameterNode.EndModify(was_modifying)
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
        result = self._robotWorkflowFacade.lockBase()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def onUnlockRobotBaseMount(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
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
        try:
            qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
            result = self._robotWorkflowFacade.generateWorkspaceCloud()
            if not result.success:
                raise RuntimeError(result.message)
            self.ui.robotWorkspaceStatusLabel.text = result.message + " " + _(
                "Every accepted TCP point retains MoveIt FK/static-validity provenance. "
                "Only the reported bounded subset has explicit Task Home path evidence; "
                "unevaluated points must not be treated as connected."
            )
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #207227;"
            self.ui.clearRobotWorkspaceButton.enabled = True
            self._updateStep6PlanningUi(result.message)
        except (RuntimeError, ValueError) as exc:
            self.ui.robotWorkspaceStatusLabel.text = str(exc)
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b00020;"
            self._updateStep6PlanningUi(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))
        finally:
            qt.QApplication.restoreOverrideCursor()

    def onClearRobotWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        self.logic.deleteRobotWorkspaceModel()
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.invalidateWorkspaceRuntimeValidation()
        self.ui.robotWorkspaceStatusLabel.text = _("No workspace cloud generated.")
        self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
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

    def onPreviewTrajectoryMotion(self, checked: bool = False) -> None:
        del checked
        if not self._robotWorkflowFacade:
            return
        self.onStopTrajectoryMotion()
        result = self._robotWorkflowFacade.previewPlan(
            on_progress=lambda _index, _count: self._updateRobotPlacement(),
            on_finished=self._onFacadePreviewFinished,
        )
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onFacadePreviewFinished(self, result) -> None:
        self._updateRobotPlacement()
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

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
