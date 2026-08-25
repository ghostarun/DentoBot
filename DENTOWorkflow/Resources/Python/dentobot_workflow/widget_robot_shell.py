"""Extracted robot application shell methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotShellWidgetMixin:
    def _setupRobotSimulationShellPanel(self) -> None:
        if self._robotSimulationPanel is not None:
            return
        self._robotSimulationPanel = DENTORobotSimulationPanel(
            self.ui.robotPlacementCollapsibleButton,
            {
                "connect": self._onShellConnectRobot,
                "disconnect": self._onShellDisconnectRobot,
                "load_fallback": self._onShellLoadFallbackRobot,
                "create_goal": self._onShellCreateTcpGoal,
                "solve_ik": self._onShellSolveIk,
                "plan_goal": self._onShellPlanGoal,
                "refresh": self._refreshShellRobotCapabilities,
                "sync_collision": self._onShellSyncCollisionScene,
                "check_state": self._onShellCheckRobotState,
                "enable_cbct_rendering": self._onStep6EnableCbctRendering,
                "cbct_preset": self._onStep6CbctPresetChanged,
                "create_proxy": self._onStep6CreateForeheadProxy,
                "placement_review": self._onStep6PlacementReview,
                "appearance_changed": self._onStep6AppearanceChanged,
                "save_home": self._onStep6SaveTaskHome,
                "apply_home": self._onStep6ApplyTaskHome,
                "review_limits": self._onStep6ReviewAssistedLimits,
                "confirm_task": self._onStep6ConfirmTask,
                "expert_diagnostics": self._onStep6OpenExpertDiagnostics,
                "plan_approach": self._onStep6PlanApproach,
                "preview_approach": self._onStep6PreviewApproach,
                "plan_drilling": self._onStep6PlanDrilling,
                "preview_drilling": self._onStep6PreviewDrilling,
            },
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.visualizationGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.homeGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.workspaceReviewGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.runtimeGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.goalGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.collisionGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.approachGroup
        )
        self.ui.robotPlacementVerticalLayout.addWidget(
            self._robotSimulationPanel.drillingGroup
        )
        self.ui.robotPlacementCollapsibleButton.text = _(
            "Step 6 — Native Placement-to-Task Simulation"
        )
        self.ui.robotPlacementDescriptionLabel.text = _(
            "Validate the case, place the local robot in CBCT context, save Task "
            "Home, review workspace-assisted limits, connect ROS/MoveIt, confirm "
            "one immutable task, then preview guarded approach and drilling phases."
        )
        self.ui.step6MountLockGroupBox.title = _("6.1 — Local Robot and Provisional Base")
        self.ui.step6TaskJointLimitsGroupBox.title = _("6.2 — Joint State for Task Home")
        self.ui.step6WorkspaceGroupBox.title = _("6.3 — Workspace and Assisted Limits")
        self.ui.step6TrajectoryPlanningGroupBox.visible = False
        self.ui.ros2MotionControlGroupBox.visible = False

    def _refreshShellRobotCapabilities(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        self._robotSimulationPanel.updateCapabilities(
            self._robotWorkflowFacade.capabilities()
        )

    def _onShellConnectRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.connect(open_motion_module=False)
        self._robotSimulationPanel.showRuntimeResult(result)
        if result.success:
            self._updateRobotPlacement()
            self._applyStep6RecommendedView()
        else:
            slicer.util.errorDisplay(result.message)
        self._refreshShellRobotCapabilities()

    def _onShellDisconnectRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.disconnect()
        self._robotSimulationPanel.showRuntimeResult(result)
        if result.success:
            self._updateRobotPlacement()
        else:
            slicer.util.errorDisplay(result.message)
        self._refreshShellRobotCapabilities()

    def _onShellLoadFallbackRobot(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.loadRobot()
        self._robotSimulationPanel.showRuntimeResult(result)
        if result.success:
            self._updateRobotPlacement()
            self.onFrameStep6ResearchWorkspace()
        else:
            slicer.util.errorDisplay(result.message)
        self._refreshShellRobotCapabilities()

    def _onShellCreateTcpGoal(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.ensureTcpGoal()
        self._robotSimulationPanel.showGoalResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellSolveIk(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.solveIk()
        self._robotSimulationPanel.showGoalResult(result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellPlanGoal(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.planToGoal()
        self._robotSimulationPanel.showGoalResult(result)
        self._step6MotionPlan = result.payload if result.success else None
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellSyncCollisionScene(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.syncPlanningScene()
        self._robotSimulationPanel.showCollisionResult(result)
        self._refreshShellRobotCapabilities()
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onShellCheckRobotState(self) -> None:
        if not self._robotSimulationPanel or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.checkStateValidity()
        self._robotSimulationPanel.showCollisionResult(result)
        if not result.success and result.code != "state_invalid":
            slicer.util.errorDisplay(result.message)

    def _setStep6PanelResult(self, label, result) -> None:
        if label is None:
            return
        label.text = result.message
        label.setProperty("dentobotState", "ok" if result.success else "error")
        label.style().unpolish(label)
        label.style().polish(label)

    def _onStep6EnableCbctRendering(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        try:
            node = self.logic.enableStep6CbctVolumeRendering(
                self._parameterNode,
                self._robotSimulationPanel.cbctPreset(),
            )
            self._robotSimulationPanel.setAppearance(
                "cbct", True, self._parameterNode.step6CbctOpacity
            )
            self._robotSimulationPanel.visualizationStatusLabel.text = _(
                "Enabled one display-only CBCT renderer (%1); source voxel geometry is unchanged."
            ).replace("%1", node.GetName())
            self._applyStep6RecommendedView()
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)
            slicer.util.errorDisplay(str(exc))

    def _onStep6CbctPresetChanged(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        try:
            changed = self.logic.applyStep6CbctRenderingPreset(
                self._parameterNode,
                self._robotSimulationPanel.cbctPreset(),
                createIfMissing=False,
            )
            self._robotSimulationPanel.visualizationStatusLabel.text = (
                _("Updated CBCT intensity appearance; geometry was not changed.")
                if changed
                else _("Enable CBCT 3D Context before selecting an appearance preset.")
            )
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)

    def _onStep6CreateForeheadProxy(self) -> None:
        if not self._parameterNode or not self.logic or not self._robotSimulationPanel:
            return
        try:
            proxy = self.logic.createOrUpdateStep6ForeheadProxy(self._parameterNode)
            self._parameterNode.robotForeheadProxyModel = proxy
            self._robotSimulationPanel.setAppearance(
                "forehead_proxy", True, self._parameterNode.step6ForeheadProxyOpacity
            )
            self._robotSimulationPanel.visualizationStatusLabel.text = _(
                "Created the curved Unregistered / Provisional / Visualization-only forehead envelope."
            )
            self._updateWorkflowViewControls()
        except (RuntimeError, ValueError) as exc:
            self._robotSimulationPanel.visualizationStatusLabel.text = str(exc)
            slicer.util.errorDisplay(str(exc))

    def _onStep6PlacementReview(self) -> None:
        if not self._robotSimulationPanel:
            return
        self._applyStep6RecommendedView()
        self.onFrameWorkflowView()
        self._robotSimulationPanel.visualizationStatusLabel.text = _(
            "Applied Robot + CBCT Placement Review and framed the union of visible case, robot, goal, mount, and proxy bounds."
        )

    def _onStep6AppearanceChanged(
        self,
        key: str,
        visible: bool,
        opacity: float,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        self.logic.setStep6Appearance(
            self._parameterNode,
            key,
            visible=visible,
            opacity=opacity,
        )
        self._updateWorkflowViewControls()

    def _onStep6SaveTaskHome(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.saveTaskHome()
        self._setStep6PanelResult(self._robotSimulationPanel.homeStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6ApplyTaskHome(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.applyTaskHome()
        self._setStep6PanelResult(self._robotSimulationPanel.homeStatusLabel, result)
        if result.success:
            self._updateRobotPlacement()
        else:
            slicer.util.errorDisplay(result.message)

    def _onStep6ReviewAssistedLimits(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.reviewAssistedLimits()
        self._setStep6PanelResult(
            self._robotSimulationPanel.workspaceReviewStatusLabel, result
        )
        if result.success:
            self._applyTaskJointLimitsToJointSpinboxes()
        else:
            slicer.util.errorDisplay(result.message)
        self._updateStep6PlanningUi(result.message, error=not result.success)

    def _onStep6ConfirmTask(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.confirmTask()
        self._robotSimulationPanel.showRuntimeResult(result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6OpenExpertDiagnostics(self) -> None:
        ready, message = prepare_dentobot_motion_diagnostics()
        if not ready:
            slicer.util.errorDisplay(message)
            return
        self.onOpenViewControlsPalette()
        self._ensureStep6ExpertReturnToolbar()
        if self._applicationShell and self._applicationShell.active:
            self._applicationShell.setExpertMode(True)
        self._step6ExpertDiagnosticHandoffActive = True
        slicer.util.selectModule("ROS2MotionControl")

    def _ensureStep6ExpertReturnToolbar(self) -> None:
        mainWindow = slicer.util.mainWindow()
        if mainWindow is None:
            return
        toolbar = mainWindow.findChild("QToolBar", "DENTOBOTExpertReturnToolbar")
        if toolbar is None:
            toolbar = qt.QToolBar(_("DENTOBOT Expert Diagnostics"), mainWindow)
            toolbar.objectName = "DENTOBOTExpertReturnToolbar"
            action = toolbar.addAction(_("Return to Robot Simulation"))
            action.objectName = "DENTOBOTReturnToRobotSimulationAction"
            action.connect("triggered(bool)", self._onReturnFromStep6ExpertDiagnostics)
            mainWindow.addToolBar(qt.Qt.TopToolBarArea, toolbar)
        self._step6ExpertReturnToolbar = toolbar
        toolbar.show()
        toolbar.raise_()

    def _onReturnFromStep6ExpertDiagnostics(self, checked: bool = False) -> None:
        del checked
        self._step6ExpertDiagnosticHandoffActive = False
        if self._step6ExpertReturnToolbar:
            self._step6ExpertReturnToolbar.hide()
        slicer.util.selectModule("DENTOWorkflow")
        qt.QTimer.singleShot(0, lambda: self._setWorkflowStage(10))
        qt.QTimer.singleShot(0, self.onOpenViewControlsPalette)

    def _onStep6PlanApproach(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.planApproachPhase()
        self._setStep6PanelResult(self._robotSimulationPanel.approachStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PhasePreviewFinished(self, label, result) -> None:
        self._setStep6PanelResult(label, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)

    def _onStep6PreviewApproach(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.previewPhase(
            MotionPhase.APPROACH.value,
            on_progress=lambda _index, _count: self._updateRobotPlacement(),
            on_finished=lambda outcome: self._onStep6PhasePreviewFinished(
                self._robotSimulationPanel.approachStatusLabel, outcome
            ),
        )
        self._setStep6PanelResult(self._robotSimulationPanel.approachStatusLabel, result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PlanDrilling(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.planDrillingPhase()
        self._setStep6PanelResult(self._robotSimulationPanel.drillingStatusLabel, result)
        self._updateStep6PlanningUi(result.message, error=not result.success)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onStep6PreviewDrilling(self) -> None:
        if not self._robotWorkflowFacade or not self._robotSimulationPanel:
            return
        result = self._robotWorkflowFacade.previewPhase(
            MotionPhase.DRILLING.value,
            on_progress=lambda _index, _count: self._updateRobotPlacement(),
            on_finished=lambda outcome: self._onStep6PhasePreviewFinished(
                self._robotSimulationPanel.drillingStatusLabel, outcome
            ),
        )
        self._setStep6PanelResult(self._robotSimulationPanel.drillingStatusLabel, result)
        if not result.success:
            slicer.util.errorDisplay(result.message)

    def _onApplicationShellSubstepSelected(
        self,
        workspace_id: str,
        substep_index: int,
    ) -> None:
        if workspace_id != "robot_simulation":
            return
        self._configureRobotSimulationShellSubstep(substep_index)

    def _configureRobotSimulationShellSubstep(self, substep_index: int) -> None:
        if not self._robotSimulationPanel:
            return
        index = max(0, min(int(substep_index), 6))
        groups = (
            self.ui.step6PlanningContextGroupBox,
            self.ui.step6MountLockGroupBox,
            self.ui.step6TaskJointLimitsGroupBox,
            self.ui.step6WorkspaceGroupBox,
            self.ui.step6TrajectoryPlanningGroupBox,
            self._robotSimulationPanel.runtimeGroup,
            self._robotSimulationPanel.goalGroup,
            self._robotSimulationPanel.collisionGroup,
            self._robotSimulationPanel.visualizationGroup,
            self._robotSimulationPanel.homeGroup,
            self._robotSimulationPanel.workspaceReviewGroup,
            self._robotSimulationPanel.approachGroup,
            self._robotSimulationPanel.drillingGroup,
        )
        for group in groups:
            group.visible = False
        visible_by_substep = {
            0: (self.ui.step6PlanningContextGroupBox,),
            1: (
                self._robotSimulationPanel.visualizationGroup,
                self.ui.step6MountLockGroupBox,
            ),
            2: (
                self.ui.step6TaskJointLimitsGroupBox,
                self._robotSimulationPanel.homeGroup,
            ),
            3: (
                self.ui.step6WorkspaceGroupBox,
                self._robotSimulationPanel.workspaceReviewGroup,
            ),
            4: (
                self._robotSimulationPanel.runtimeGroup,
                self._robotSimulationPanel.collisionGroup,
            ),
            5: (self._robotSimulationPanel.approachGroup,),
            6: (self._robotSimulationPanel.drillingGroup,),
        }
        for group in visible_by_substep[index]:
            group.visible = True
        self.ui.ros2MotionControlGroupBox.visible = False
        self.ui.robotPlacementDescriptionLabel.visible = index == 0
        if index in {4, 5, 6}:
            self._refreshShellRobotCapabilities()

    def _restoreLegacyRobotSimulationGroups(self) -> None:
        if not self._robotSimulationPanel:
            return
        for group in (
            self.ui.step6PlanningContextGroupBox,
            self.ui.step6MountLockGroupBox,
            self.ui.step6TaskJointLimitsGroupBox,
            self.ui.step6WorkspaceGroupBox,
            self._robotSimulationPanel.visualizationGroup,
            self._robotSimulationPanel.homeGroup,
            self._robotSimulationPanel.workspaceReviewGroup,
            self._robotSimulationPanel.runtimeGroup,
            self._robotSimulationPanel.collisionGroup,
            self._robotSimulationPanel.approachGroup,
            self._robotSimulationPanel.drillingGroup,
        ):
            group.visible = True
        self.ui.step6TrajectoryPlanningGroupBox.visible = False
        self.ui.ros2MotionControlGroupBox.visible = False
        self.ui.robotPlacementDescriptionLabel.visible = True
        self._robotSimulationPanel.goalGroup.visible = False
