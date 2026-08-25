"""Extracted Step 6 and robot UI methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class RobotWidgetMixin:
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

    def _robotJointPositionsSi(self) -> dict[str, float]:
        if not self._parameterNode:
            return joint_positions_si_from_display(0, 0, 0, 0, 0, 0)
        return joint_positions_si_from_display(
            self._parameterNode.robotJoint1Deg,
            self._parameterNode.robotJoint2Mm,
            self._parameterNode.robotJoint3Deg,
            self._parameterNode.robotJoint4Mm,
            self._parameterNode.robotJoint5Deg,
            self._parameterNode.robotJoint6Deg,
        )

    def _setupRobotKeyboardShortcuts(self) -> None:
        """Create disabled shortcuts; Step 6 and the explicit toggle gate them."""

        if self._robotKeyboardShortcuts:
            return
        bindings = (
            ("Left", 0, None, -1.0),
            ("Right", 0, None, 1.0),
            ("Down", 1, None, -1.0),
            ("Up", 1, None, 1.0),
            ("PgDown", 2, None, -1.0),
            ("PgUp", 2, None, 1.0),
            ("Shift+Down", None, 0, -1.0),
            ("Shift+Up", None, 0, 1.0),
            ("Shift+Left", None, 2, -1.0),
            ("Shift+Right", None, 2, 1.0),
        )
        parent = slicer.util.mainWindow() or self.parent
        for keySequence, translationAxis, rotationAxis, direction in bindings:
            shortcut = qt.QShortcut(qt.QKeySequence(keySequence), parent)
            shortcut.objectName = f"robotNudgeShortcut{keySequence.replace('+', '')}"
            shortcut.context = qt.Qt.ApplicationShortcut
            shortcut.enabled = False
            shortcut.connect(
                "activated()",
                lambda ta=translationAxis, ra=rotationAxis, d=direction:
                    self._onRobotKeyboardNudge(ta, ra, d),
            )
            self._robotKeyboardShortcuts.append(shortcut)

    def _disableRobotKeyboardShortcuts(self) -> None:
        for shortcut in self._robotKeyboardShortcuts:
            shortcut.enabled = False

    def _updateRobotKeyboardShortcutState(self) -> None:
        if not hasattr(self, "ui"):
            return
        stageEntries = self._workflowStageEntries()
        robotStageActive = bool(
            stageEntries
            and int(self.ui.workflowStageComboBox.currentIndex)
            == len(stageEntries) - 1
        )
        enabled = bool(
            robotStageActive
            and self._parameterNode
            and not self._parameterNode.robotBaseMountLocked
            and self._parameterNode.robotKeyboardNudgeEnabled
            and self.logic
            and self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            )
        )
        for shortcut in self._robotKeyboardShortcuts:
            shortcut.enabled = enabled
        self._setRobotTransformInteractionVisible(robotStageActive)

    def _onRobotKeyboardNudge(
        self,
        translationAxis: int | None,
        rotationAxis: int | None,
        direction: float,
    ) -> None:
        focusWidget = qt.QApplication.focusWidget()
        if focusWidget and (
            focusWidget.inherits("QAbstractSpinBox")
            or focusWidget.inherits("QLineEdit")
            or focusWidget.inherits("QTextEdit")
        ):
            return
        self._nudgeRobotBase(translationAxis, rotationAxis, direction)

    def _setRobotTransformInteractionVisible(self, visible: bool) -> None:
        if not self.logic:
            return
        baseTransform = (
            self._parameterNode.robotBaseTransform if self._parameterNode else None
        )
        planeNode = self._parameterNode.robotMountPlane if self._parameterNode else None
        if self.logic.isRobotBaseTransformNode(baseTransform):
            baseTransform.CreateDefaultDisplayNodes()
            displayNode = baseTransform.GetDisplayNode()
            if displayNode:
                for methodName, value in (
                    ("SetEditorVisibility", bool(visible)),
                    ("SetHandlesInteractive", bool(visible)),
                    ("SetTranslationHandleVisibility", bool(visible)),
                    ("SetRotationHandleVisibility", bool(visible)),
                    ("SetScaleHandleVisibility", False),
                ):
                    method = getattr(displayNode, methodName, None)
                    if method:
                        method(value)
        if self.logic.isRobotMountPlaneNode(planeNode):
            planeNode.CreateDefaultDisplayNodes()
            displayNode = planeNode.GetDisplayNode()
            if displayNode:
                displayNode.SetHandlesInteractive(bool(visible))
                displayNode.SetTranslationHandleVisibility(bool(visible))
                displayNode.SetRotationHandleVisibility(bool(visible))
                displayNode.SetScaleHandleVisibility(False)

    def _bindRobotPlacementNodes(self, baseTransform, planeNode) -> None:
        if self._robotBaseTransformNode is not baseTransform:
            if self._robotBaseTransformNode:
                self.removeObserver(
                    self._robotBaseTransformNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onRobotPlacementNodeModified,
                )
            self._robotBaseTransformNode = baseTransform
            self._lastRobotBasePoseFingerprint = (
                self.logic.robotBasePoseFingerprint(baseTransform)
                if self.logic and baseTransform
                else ""
            )
            if baseTransform:
                self.addObserver(
                    baseTransform,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onRobotPlacementNodeModified,
                )
        if self._robotMountPlaneNode is not planeNode:
            if self._robotMountPlaneNode:
                self.removeObserver(
                    self._robotMountPlaneNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onRobotPlacementNodeModified,
                )
            self._robotMountPlaneNode = planeNode
            if planeNode:
                self.addObserver(
                    planeNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onRobotPlacementNodeModified,
                )

    def _onRobotPlacementNodeModified(self, caller=None, event=None) -> None:
        del event
        if self._updatingRobotPlacementUI:
            return
        if (
            self.logic
            and self._parameterNode
            and caller is self._parameterNode.robotBaseTransform
        ):
            poseFingerprint = self.logic.robotBasePoseFingerprint(caller)
            if (
                self._lastRobotBasePoseFingerprint
                and poseFingerprint != self._lastRobotBasePoseFingerprint
            ):
                self._parameterNode.step6BasePlacementRevision = max(
                    0, int(self._parameterNode.step6BasePlacementRevision)
                ) + 1
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Robot base pose changed."),
                    makeBaseStale=bool(self._parameterNode.robotBaseMountLocked),
                )
                self._step6MotionPlan = None
                if self._robotWorkflowFacade:
                    self._robotWorkflowFacade.clearTransientState()
            self._lastRobotBasePoseFingerprint = poseFingerprint
            workspace = self.logic.robotWorkspaceModelNode()
            if workspace:
                workspace.SetAttribute("DENTOBOT.WorkspaceState", "Stale")
                self.ui.robotWorkspaceStatusLabel.text = _(
                    "Base placement changed. Regenerate before interpreting the "
                    "collision-filtered workspace."
                )
                self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
        self._updateRobotPlacementStatus()

    def _updateRobotPlacementStatus(self, message: str = "") -> None:
        if not self._parameterNode or not self.logic:
            return
        baseTransform = self._parameterNode.robotBaseTransform
        modelCount = len(self.logic.robotModelNodes())
        if message:
            status = message
            style = "color: #207227;"
        elif self.logic.isRos2MotionControlActive(baseTransform):
            status = _("ROS robot is in the viewport. Place the mount, then lock.")
            style = "color: #207227;"
        elif not self.logic.isRobotBaseTransformNode(baseTransform) or modelCount != 7:
            status = _("Choose a scene in 6.0, then load the local MRML robot in 6.1.")
            style = "color: #b36b00;"
        else:
            matrix = vtk.vtkMatrix4x4()
            baseTransform.GetMatrixTransformToWorld(matrix)
            origin = tuple(matrix.GetElement(axis, 3) for axis in range(3))
            status = _(
                "Robot loaded (%1/7 links). Base RAS: X %2, Y %3, Z %4 mm."
            ).replace("%1", str(modelCount)).replace(
                "%2", f"{origin[0]:.2f}"
            ).replace("%3", f"{origin[1]:.2f}").replace(
                "%4", f"{origin[2]:.2f}"
            )
            style = "color: #207227;"
        self.ui.robotPlacementStatusLabel.text = status
        self.ui.robotPlacementStatusLabel.styleSheet = style

    def _updateRobotPlacement(self) -> None:
        if not self._parameterNode or not self.logic or not hasattr(self, "ui"):
            return
        baseTransform = self._parameterNode.robotBaseTransform
        planeNode = self._parameterNode.robotMountPlane
        self._bindRobotPlacementNodes(baseTransform, planeNode)
        baseValid = self.logic.isRobotBaseTransformNode(baseTransform)
        planeValid = self.logic.isRobotMountPlaneNode(planeNode)
        modelCount = len(self.logic.robotModelNodes())
        stageEntries = self._workflowStageEntries()
        robotStageActive = bool(
            stageEntries
            and int(self.ui.workflowStageComboBox.currentIndex)
            == len(stageEntries) - 1
        )
        if baseValid and modelCount:
            self.logic.updateRobotJointPoses(self._robotJointPositionsSi())
        self._updatingRobotPlacementUI = True
        try:
            for button in (
                self.ui.snapRobotBaseToPlaneButton,
                self.ui.frameRobotButton,
                self.ui.resetRobotJointsButton,
                self.ui.resetRobotBaseButton,
                self.ui.deleteRobotSetupButton,
                self.ui.robotXMinusButton,
                self.ui.robotXPlusButton,
                self.ui.robotYMinusButton,
                self.ui.robotYPlusButton,
                self.ui.robotZMinusButton,
                self.ui.robotZPlusButton,
                self.ui.robotRxMinusButton,
                self.ui.robotRxPlusButton,
                self.ui.robotRyMinusButton,
                self.ui.robotRyPlusButton,
                self.ui.robotRzMinusButton,
                self.ui.robotRzPlusButton,
            ):
                button.enabled = baseValid
            self.ui.snapRobotBaseToPlaneButton.enabled = baseValid and planeValid
            self.ui.flipRobotMountPlaneButton.enabled = planeValid
            self.ui.robotKeyboardNudgeCheckBox.enabled = baseValid
            phantomLoaded = bool(
                self._parameterNode.draftPhantomSkullModel
                and self._parameterNode.draftPhantomMandibleModel
            )
            self.ui.frameRobotButton.enabled = bool(
                modelCount or self.logic.draftPhantomModelNodes()
            )
            self.ui.deleteDraftPhantomButton.enabled = bool(
                self.logic.draftPhantomModelNodes()
            )
            self._updateDraftJawLandmarkControls(phantomLoaded=phantomLoaded)
            self.ui.resetDraftJawButton.enabled = self.logic.isDraftJawTransformNode(
                self._parameterNode.draftJawTransform
            )
        finally:
            self._updatingRobotPlacementUI = False
        self._updateRobotPlacementStatus()
        self._updateDraftPhantomStatus()
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateRos2MotionControlStatus()
        self._updateRobotKeyboardShortcutState()
        if self._parameterNode and self.logic:
            if self._parameterNode.robotBaseMountLocked:
                self.logic.setRobotBaseMountLocked(self._parameterNode, True)
            try:
                self._applyTaskJointLimitsToJointSpinboxes()
            except ValueError:
                pass
        self._updateStep6PlanningUi()
        if robotStageActive:
            self._updateWorkflowViewControls()

    def _updateRos2MotionControlStatus(self, message: str = "") -> None:
        if not hasattr(self, "ui"):
            return
        base_transform = (
            self._parameterNode.robotBaseTransform if self._parameterNode else None
        )
        ros2_active = (
            self.logic.isRos2MotionControlActive(base_transform)
            if self.logic and base_transform
            else False
        )
        stage_entries = self._workflowStageEntries()
        step6_stage_active = bool(
            stage_entries
            and int(self.ui.workflowStageComboBox.currentIndex)
            == len(stage_entries) - 1
        )
        if message:
            status = message
            style = "color: #c62828;" if "failed" in message.lower() else "color: #207227;"
        elif not ros2_active and not step6_stage_active:
            status = _(
                "ROS 2 / MoveIt is inactive for this workflow stage. It is "
                "created in the MRML scene only when Step 6 is opened or Connect is used."
            )
            style = "color: #666666;"
        elif ros2_active:
            guard_status = joint_command_status()
            if guard_status is not None and not guard_status.accepted:
                pair = ""
                if guard_status.first_body or guard_status.second_body:
                    pair = " (%s ↔ %s)" % (
                        guard_status.first_body or "?",
                        guard_status.second_body or "?",
                    )
                self.ui.ros2MotionControlStatusLabel.text = _(
                    "Collision guard rejected the last manual move: %1%2"
                ).replace("%1", guard_status.reason).replace("%2", pair)
                self.ui.ros2MotionControlStatusLabel.styleSheet = "color: #c62828;"
                self._updateStep6PlanningUi()
                return
            ok, nodes, _cli = ros2_node_list()
            slicer_present = ok and ROS2_DEFAULT_SLICER_NODE in {
                name.lstrip("/") for name in nodes
            }
            if slicer_present:
                status = _(
                    "ROS 2 motion control is active. /slicer is present. "
                    "MRML link meshes are hidden while the SlicerROS2 robot "
                    "follows /joint_states."
                )
            else:
                status = _(
                    "ROS 2 motion control is marked active but /slicer was not "
                    "found. Reload DENTO Workflow."
                )
            style = "color: #207227;" if slicer_present else "color: #c62828;"
        else:
            stack_running, stack_hint = description_stack_running()
            if stack_running:
                status = _(
                    "The external DENTOBOT description + MoveIt stack is ready. "
                    "Connect to load the robot in SlicerROS2 Motion Control."
                )
            else:
                status = _(
                    "The external ROS 2 + MoveIt simulation stack is not ready. "
                    "Restart Slicer with Workspace/scripts/launch-dentoworkflow.bash."
                )
                if stack_hint:
                    status = f"{status} ({stack_hint})"
            style = "color: #b36b00;"
        self.ui.ros2MotionControlStatusLabel.text = status
        self.ui.ros2MotionControlStatusLabel.styleSheet = style
        self._updateStep6PlanningUi()

    def onConnectRos2MotionControl(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.connect(open_motion_module=False)
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 connect failed: %1").replace("%1", result.message)
            )
            slicer.util.errorDisplay(result.message)
            return
        self._updateRobotPlacement()
        self._applyStep6RecommendedView()
        self._updateRos2MotionControlStatus(result.message)

    def onDisconnectRos2MotionControl(self, checked: bool = False) -> None:
        del checked
        if not self.logic or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.disconnect()
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 disconnect failed: %1").replace("%1", result.message)
            )
            slicer.util.errorDisplay(result.message)
            return
        self._updateRobotPlacement()
        self._updateRos2MotionControlStatus(result.message)

    def _clearRobotPlacement(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._bindRobotPlacementNodes(None, None)
        self._disableRobotKeyboardShortcuts()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.robotBaseTransformSelector.setCurrentNode(None)
            self.ui.robotMountPlaneSelector.setCurrentNode(None)
            self.ui.robotPlacementStatusLabel.text = _(
                "Load the seven articulated robot meshes to begin placement."
            )
            self.ui.robotPlacementStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingRobotPlacementUI = False

    def _updateDraftPhantomStatus(self, message: str = "", error: bool = False) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.draftOpenMouthStatusLabel.text = message
            self.ui.draftOpenMouthStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        transform = self._parameterNode.draftJawTransform
        if self.logic.isDraftJawTransformNode(transform):
            angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
            gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft mouth open: pure TMJ hinge rotation %1°, measured incisor gap %2 mm."
            ).replace("%1", angle).replace("%2", gap)
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #207227;"
        elif self.logic.draftPhantomModelNodes():
            pointCount = (
                self._parameterNode.draftJawLandmarks.GetNumberOfDefinedControlPoints()
                if self.logic.isDraftJawLandmarksNode(
                    self._parameterNode.draftJawLandmarks
                )
                else 0
            )
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Draft phantom loaded. Jaw landmarks placed: %1/4."
            ).replace("%1", str(pointCount))
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"
        else:
            self.ui.draftOpenMouthStatusLabel.text = _(
                "Load the local generic phantom to begin."
            )
            self.ui.draftOpenMouthStatusLabel.styleSheet = "color: #b36b00;"

    def _bindStep6CaseJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._step6CaseJawLandmarksNode:
            return
        if self._step6CaseJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._step6CaseJawLandmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )
        self._step6CaseJawLandmarksNode = landmarksNode
        if landmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    landmarksNode,
                    landmarkEvent,
                    self._onStep6CaseJawLandmarksModified,
                )

    def _markStep6CaseJawOpeningStale(self, reason: str) -> None:
        if not self._parameterNode or not self.logic:
            return
        transform = self._parameterNode.step6CaseJawTransform
        if self.logic.isStep6CaseJawTransformNode(transform):
            transform.SetAttribute("DENTOBOT.GeometryState", "Stale")
            transform.SetAttribute("DENTOBOT.StaleReason", reason)
        model = self._parameterNode.step6OpenedLowerJawModel
        if self.logic.isStep6OpenedLowerJawModelNode(model):
            model.SetAttribute("DENTOBOT.GeometryState", "Stale")
        self.logic.invalidateStep6TaskConfirmation(
            self._parameterNode,
            reason,
            makeBaseStale=True,
        )
        self.logic.deleteRobotWorkspaceModel()
        self._step6MotionPlan = None
        if self._robotWorkflowFacade:
            self._robotWorkflowFacade.clearTransientState()

    def _onStep6CaseJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller, event
        if (
            self._updatingStep6CaseJawLandmarks
            or not self._parameterNode
            or not self.logic
        ):
            return
        node = self._step6CaseJawLandmarksNode
        if not node or not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        self._updatingStep6CaseJawLandmarks = True
        try:
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
        except ValueError:
            return
        finally:
            self._updatingStep6CaseJawLandmarks = False
        if self.logic.isStep6CaseJawTransformNode(
            self._parameterNode.step6CaseJawTransform
        ):
            self._markStep6CaseJawOpeningStale(
                _("Case jaw landmarks changed; apply the mouth opening again.")
            )
        if summary["isComplete"]:
            self.logic.stopTrajectoryPlacement()
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def _updateStep6CaseJawOpeningControls(self) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        imported = bool(self._parameterNode.step6PlanningContextImported)
        blocked = bool(
            self._parameterNode.robotBaseMountLocked
            or self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
        )
        node = self._parameterNode.step6CaseJawLandmarks
        summary = None
        if node and self.logic.isStep6CaseJawLandmarksNode(node):
            try:
                summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        complete = bool(summary and summary["isComplete"])
        labels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.step6CaseJawOpeningGroupBox.enabled = imported
            self.ui.createStep6CaseJawLandmarksButton.enabled = bool(
                imported and not blocked and not complete
            )
            self.ui.createStep6CaseJawLandmarksButton.text = (
                labels[pointCount]
                if pointCount < len(labels)
                else _("All landmarks placed")
            )
            self.ui.clearStep6CaseJawLandmarksButton.enabled = bool(
                imported and not blocked and pointCount > 0
            )
            self.ui.applyStep6CaseJawOpeningButton.enabled = bool(
                imported and not blocked and complete
            )
            self.ui.resetStep6CaseJawOpeningButton.enabled = bool(
                imported
                and not blocked
                and (
                    self.logic.isStep6CaseJawTransformNode(
                        self._parameterNode.step6CaseJawTransform
                    )
                    or self.logic.isStep6OpenedLowerJawModelNode(
                        self._parameterNode.step6OpenedLowerJawModel
                    )
                )
            )
        finally:
            self._updatingRobotPlacementUI = False

    def _updateStep6CaseJawOpeningStatus(
        self,
        message: str = "",
        error: bool = False,
    ) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if message:
            self.ui.step6CaseJawOpeningStatusLabel.text = message
            self.ui.step6CaseJawOpeningStatusLabel.styleSheet = (
                "color: #b00020;" if error else "color: #207227;"
            )
            return
        if not self._parameterNode.step6PlanningContextImported:
            text = _("Import the Steps 0–5 planning package first.")
            style = "color: #b36b00;"
        else:
            issues = self.logic.step6CaseJawOpeningFreshnessIssues(
                self._parameterNode
            )
            if issues:
                node = self._parameterNode.step6CaseJawLandmarks
                pointCount = (
                    node.GetNumberOfDefinedControlPoints()
                    if self.logic.isStep6CaseJawLandmarksNode(node)
                    else 0
                )
                text = (
                    _("Case jaw landmarks placed: %1/4. %2")
                    .replace("%1", str(pointCount))
                    .replace("%2", " ".join(issues))
                )
                style = "color: #b36b00;"
            else:
                transform = self._parameterNode.step6CaseJawTransform
                angle = transform.GetAttribute("DENTOBOT.HingeAngleDeg") or "--"
                gap = transform.GetAttribute("DENTOBOT.AchievedIncisorGapMm") or "--"
                model = self._parameterNode.step6OpenedLowerJawModel
                try:
                    movingCount = len(
                        json.loads(
                            model.GetAttribute("DENTOBOT.MovingSegmentIdsJson") or "[]"
                        )
                    )
                except (TypeError, json.JSONDecodeError):
                    movingCount = 0
                text = _(
                    "Case mouth open: TMJ hinge rotation %1°, measured incisor "
                    "gap %2 mm; %3 lower-jaw surface(s) drive Step 6 collision."
                ).replace("%1", angle).replace("%2", gap).replace(
                    "%3", str(movingCount)
                )
                style = "color: #207227;"
        self.ui.step6CaseJawOpeningStatusLabel.text = text
        self.ui.step6CaseJawOpeningStatusLabel.styleSheet = style

    def onCreateStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            if not self._parameterNode.step6PlanningContextImported:
                raise ValueError(_("Import the Steps 0–5 planning package first."))
            node = self.logic.ensureStep6CaseJawLandmarksNode(
                self._parameterNode.step6CaseJawLandmarks
            )
            self._parameterNode.step6CaseJawLandmarks = node
            self._bindStep6CaseJawLandmarksNode(node)
            summary = self.logic.getStep6CaseJawLandmarkSummary(node)
            if summary["isComplete"]:
                return
            self.logic.startStep6CaseJawLandmarkPlacement(node)
            landmarkIndex = summary["definedPointCount"]
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Click one point in a 2D or 3D view for %1, then press the "
                    "placement button for the next landmark."
                ).replace(
                    "%1",
                    self.logic.draftJawLandmarkPlacementHints()[landmarkIndex],
                )
            )
            self._updateStep6CaseJawOpeningControls()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearStep6CaseJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.step6CaseJawLandmarks
        if not self.logic.isStep6CaseJawLandmarksNode(node):
            return
        try:
            self.logic.stopTrajectoryPlacement()
            if (
                self._parameterNode.step6CaseJawTransform
                or self._parameterNode.step6OpenedLowerJawModel
            ):
                self.logic.resetStep6CaseJawOpening(self._parameterNode)
            self._updatingStep6CaseJawLandmarks = True
            node.RemoveAllControlPoints()
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Case jaw landmarks cleared. Place Left TMJ first.")
            )
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updatingStep6CaseJawLandmarks = False
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onApplyStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            _transform, _model, _gapLine, summary = (
                self.logic.createOrUpdateStep6CaseJawOpening(self._parameterNode)
            )
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _(
                    "Applied case TMJ opening %1°; measured incisor gap %2 mm. "
                    "Continue to 6.1 with the opened planning anatomy."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
            self._applyStep6RecommendedView()
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetStep6CaseJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.resetStep6CaseJawOpening(self._parameterNode)
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
            self._updateStep6CaseJawOpeningControls()
            self._updateStep6CaseJawOpeningStatus(
                _("Case jaw reset to the closed source pose; Step 6 is blocked.")
            )
            self._updateStep6PlanningUi()
        except (RuntimeError, ValueError) as exc:
            self._updateStep6CaseJawOpeningStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onStep6CaseJawTargetGapChanged(self, value: float = 0.0) -> None:
        del value
        if (
            self._updatingFromParameterNode
            or self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
        ):
            return
        if self.logic.isStep6CaseJawTransformNode(
            self._parameterNode.step6CaseJawTransform
        ):
            self._markStep6CaseJawOpeningStale(
                _("Requested case incisor gap changed; apply the mouth opening again.")
            )
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onLoadRobotModel(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        result = self._robotWorkflowFacade.loadRobot()
        if not result.success:
            slicer.util.errorDisplay(result.message)
            return
        self._updateRobotPlacement()
        self.onFrameStep6ResearchWorkspace()
        self._applyStep6RecommendedView()
        self._updateRobotPlacementStatus(result.message)

    def onLoadDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not self._confirmStep6SceneSwitch("phantom"):
            return
        if self._parameterNode.step6PlanningContextImported:
            self._parameterNode.step6PlanningContextImported = False
        try:
            skull, mandible, models = self.logic.createOrUpdateDraftPhantom()
            self._parameterNode.draftPhantomSkullModel = skull
            self._parameterNode.draftPhantomMandibleModel = mandible
            self.onFrameStep6ResearchWorkspace()
            if self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            ):
                self.logic.positionRobotBaseNearResearchPhantom(
                    self._parameterNode.robotBaseTransform,
                    models,
                )
            self._updateRobotPlacement()
            self._applyStep6RecommendedView()
            self._updateDraftPhantomStatus(
                _(
                    "Loaded generic BodyParts3D neurocranium, maxilla, and mandible. "
                    "Place the first jaw landmark next."
                )
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onCreateDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            node = self.logic.ensureDraftJawLandmarksNode(
                self._parameterNode.draftJawLandmarks
            )
            self._parameterNode.draftJawLandmarks = node
            self._bindDraftJawLandmarksNode(node)
            summary = self.logic.getDraftJawLandmarkSummary(node)
            if summary["isComplete"]:
                return
            self.logic.startDraftJawLandmarkPlacement(node)
            self._updateRobotPlacement()
            landmarkIndex = summary["definedPointCount"]
            placementHints = self.logic.draftJawLandmarkPlacementHints()
            self._updateDraftPhantomStatus(
                _(
                    "Click one point in a 3D view for %1, then pan to the next "
                    "landmark and press the button again."
                ).replace("%1", placementHints[landmarkIndex])
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onClearDraftJawLandmarks(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode.draftJawLandmarks
        if not self.logic.isDraftJawLandmarksNode(node):
            return
        if node.GetNumberOfDefinedControlPoints() == 0:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            self.logic.resetDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
            )
            self._parameterNode.draftJawGapLine = None
            self.logic.clearDraftJawLandmarks(node)
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _("Draft jaw landmarks cleared. Place the first landmark next.")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def _bindDraftJawLandmarksNode(
        self,
        landmarksNode: vtkMRMLMarkupsFiducialNode | None,
    ) -> None:
        if landmarksNode is self._draftJawLandmarksNode:
            return
        if self._draftJawLandmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.removeObserver(
                    self._draftJawLandmarksNode,
                    landmarkEvent,
                    self._onDraftJawLandmarksModified,
                )
        self._draftJawLandmarksNode = landmarksNode
        if landmarksNode:
            for landmarkEvent in (
                vtk.vtkCommand.ModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointPositionDefinedEvent,
                slicer.vtkMRMLMarkupsNode.PointModifiedEvent,
                slicer.vtkMRMLMarkupsNode.PointRemovedEvent,
            ):
                self.addObserver(
                    landmarksNode,
                    landmarkEvent,
                    self._onDraftJawLandmarksModified,
                )

    def _onDraftJawLandmarksModified(self, caller=None, event=None) -> None:
        del caller, event
        if not self._parameterNode or not self.logic:
            return
        node = self._draftJawLandmarksNode
        if not node or not self.logic.isDraftJawLandmarksNode(node):
            return
        try:
            summary = self.logic.getDraftJawLandmarkSummary(node)
        except ValueError:
            return
        pointCount = summary["definedPointCount"]
        if pointCount >= 4:
            self.logic.stopTrajectoryPlacement()
            if not self.logic.isDraftJawTransformNode(
                self._parameterNode.draftJawTransform
            ):
                try:
                    self.onApplyDraftJawOpening()
                except (RuntimeError, ValueError) as exc:
                    self._updateDraftPhantomStatus(str(exc), error=True)
                    slicer.util.errorDisplay(str(exc))
        self._updateDraftJawLandmarkControls()
        if pointCount < 4:
            self._updateDraftPhantomStatus()

    def _updateDraftJawLandmarkControls(self, phantomLoaded: bool | None = None) -> None:
        if not hasattr(self, "ui") or not self._parameterNode or not self.logic:
            return
        if phantomLoaded is None:
            phantomLoaded = bool(
                self._parameterNode.draftPhantomSkullModel
                and self._parameterNode.draftPhantomMandibleModel
            )
        node = self._parameterNode.draftJawLandmarks
        summary = None
        if node and self.logic.isDraftJawLandmarksNode(node):
            try:
                summary = self.logic.getDraftJawLandmarkSummary(node)
            except ValueError:
                summary = None
        pointCount = summary["definedPointCount"] if summary else 0
        isComplete = bool(summary and summary["isComplete"])
        buttonLabels = self.logic.draftJawLandmarkButtonLabels()
        self._updatingRobotPlacementUI = True
        try:
            self.ui.createDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and not isComplete
            )
            self.ui.createDraftJawLandmarksButton.text = (
                buttonLabels[pointCount]
                if pointCount < len(buttonLabels)
                else _("All landmarks placed")
            )
            self.ui.clearDraftJawLandmarksButton.enabled = bool(
                phantomLoaded and pointCount > 0
            )
            self.ui.applyDraftJawOpeningButton.enabled = bool(
                phantomLoaded and isComplete
            )
        finally:
            self._updatingRobotPlacementUI = False

    def onApplyDraftJawOpening(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            transform, gapLine, summary = self.logic.createOrUpdateDraftJawOpening(
                self._parameterNode.draftPhantomMandibleModel,
                self._parameterNode.draftJawLandmarks,
                self._parameterNode.draftJawTransform,
                self._parameterNode.draftJawGapLine,
                self._parameterNode.draftJawTargetGapMm,
            )
            self._parameterNode.draftJawTransform = transform
            self._parameterNode.draftJawGapLine = gapLine
            self._updateRobotPlacement()
            self._updateDraftPhantomStatus(
                _(
                    "Draft mouth opened by pure TMJ hinge rotation %1°; measured "
                    "incisor gap %2 mm."
                )
                .replace("%1", f"{summary['angleDeg']:.2f}")
                .replace("%2", f"{summary['gapMm']:.2f}")
            )
        except (RuntimeError, ValueError) as exc:
            self._updateDraftPhantomStatus(str(exc), error=True)
            slicer.util.errorDisplay(str(exc))

    def onResetDraftJaw(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        self.logic.resetDraftJawOpening(
            self._parameterNode.draftPhantomMandibleModel,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        self._parameterNode.draftJawGapLine = None
        self._updateRobotPlacement()
        self._updateDraftPhantomStatus(_("Draft mandible reset to the closed source pose."))

    def onDeleteDraftPhantom(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        removed = self.logic.deleteDraftPhantom(
            self._parameterNode.draftJawLandmarks,
            self._parameterNode.draftJawTransform,
            self._parameterNode.draftJawGapLine,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.draftPhantomSkullModel = None
            self._parameterNode.draftPhantomMandibleModel = None
            self._parameterNode.draftJawLandmarks = None
            self._parameterNode.draftJawTransform = None
            self._parameterNode.draftJawGapLine = None
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._bindDraftJawLandmarksNode(None)
        self._updateRobotPlacement()
        logging.info("Deleted %d disposable draft phantom nodes", len(removed))

    def onCreateRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            planeNode = self.logic.createOrResetRobotMountPlane(
                self._parameterNode.robotMountPlane,
                self._parameterNode.robotBaseTransform,
            )
            self._parameterNode.robotMountPlane = planeNode
            try:
                slicer.modules.markups.logic().SetActiveListID(planeNode)
            except Exception:
                logging.debug("Could not make the robot mount plane active.")
            self._updateRobotPlacement()
            self._updateRobotPlacementStatus(
                _("Mount plane ready. Drag its handles, then click Snap Base to Plane.")
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onSnapRobotBaseToPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.snapRobotBaseToPlane(
                self._parameterNode.robotBaseTransform,
                self._parameterNode.robotMountPlane,
            )
            self._updateRobotPlacementStatus(
                _("Robot base snapped to the mount-plane origin and orientation.")
            )
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onFlipRobotMountPlane(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        planeNode = self._parameterNode.robotMountPlane
        if not self.logic.isRobotMountPlaneNode(planeNode):
            return
        normal = np.asarray(planeNode.GetNormalWorld(), dtype=float)
        planeNode.SetNormalWorld(tuple(float(value) for value in -normal))
        self._updateRobotPlacementStatus(_("Mount-plane normal flipped."))

    def _nudgeRobotBase(
        self,
        translationAxis: int | None,
        rotationAxis: int | None,
        direction: float,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        if self._parameterNode.robotBaseMountLocked:
            return
        translation = [0.0, 0.0, 0.0]
        rotation = [0.0, 0.0, 0.0]
        if translationAxis is not None:
            translation[translationAxis] = (
                float(direction) * self._parameterNode.robotTranslationStepMm
            )
        if rotationAxis is not None:
            rotation[rotationAxis] = (
                float(direction) * self._parameterNode.robotRotationStepDeg
            )
        try:
            self.logic.nudgeRobotBase(
                self._parameterNode.robotBaseTransform,
                translationLocalMm=tuple(translation),
                rotationLocalDeg=tuple(rotation),
            )
            self._updateRobotPlacementStatus()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onRobotJointValueChanged(self, value: float) -> None:
        del value
        if (
            self._updatingRobotPlacementUI
            or not self._parameterNode
            or not self.logic
            or not self._robotWorkflowFacade
        ):
            return
        result = self._robotWorkflowFacade.requestCurrentJointState()
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 joint update failed: %1").replace("%1", result.message)
            )
            self._updateRobotPlacement()
            return
        self._updateRobotPlacementStatus()

    def onRobotBaseTransformSelectionChanged(self, transformNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotBaseTransform = transformNode
        self._updateRobotPlacement()

    def onRobotMountPlaneSelectionChanged(self, planeNode) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotMountPlane = planeNode
        self._updateRobotPlacement()

    def onDraftPhantomSelectionChanged(self, node=None) -> None:
        del node
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftPhantomSkullModel = (
            self.ui.draftPhantomSkullSelector.currentNode()
        )
        self._parameterNode.draftPhantomMandibleModel = (
            self.ui.draftPhantomMandibleSelector.currentNode()
        )
        self._updateRobotPlacement()

    def onDraftJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.draftJawLandmarks = node
        self._bindDraftJawLandmarksNode(node)
        self._updateRobotPlacement()

    def onStep6CaseJawLandmarksSelectionChanged(self, node) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        if node and self.logic and not self.logic.isStep6CaseJawLandmarksNode(node):
            slicer.util.errorDisplay(_("Select the Step 6 case jaw landmark set."))
            return
        self._parameterNode.step6CaseJawLandmarks = node
        self._bindStep6CaseJawLandmarksNode(node)
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateStep6PlanningUi()

    def onRobotKeyboardNudgeToggled(self, checked: bool) -> None:
        if self._updatingRobotPlacementUI or not self._parameterNode:
            return
        self._parameterNode.robotKeyboardNudgeEnabled = bool(checked)
        self._updateRobotKeyboardShortcutState()

    def onResetRobotJoints(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode:
            return
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotJoint1Deg = 0.0
            self._parameterNode.robotJoint2Mm = 0.0
            self._parameterNode.robotJoint3Deg = 0.0
            self._parameterNode.robotJoint4Mm = 0.0
            self._parameterNode.robotJoint5Deg = 0.0
            self._parameterNode.robotJoint6Deg = 0.0
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._updateRobotPlacement()
        self._updateRobotPlacementStatus(_("All robot joints reset to selected zero."))

    def onResetRobotBase(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        baseTransform = self._parameterNode.robotBaseTransform
        if not self.logic.isRobotBaseTransformNode(baseTransform):
            return
        matrix = vtk.vtkMatrix4x4()
        matrix.Identity()
        baseTransform.SetAndObserveTransformNodeID(None)
        baseTransform.SetMatrixTransformToParent(matrix)
        self._updateRobotPlacementStatus(_("Robot base reset to Slicer world RAS."))

    def onFrameStep6CaseScene(self, checked: bool = False) -> None:
        """Show the imported case in slice and 3D views (not the phantom workspace)."""
        del checked
        if not self._parameterNode or not self.logic:
            return
        self._showStep6CaseVolumeInSliceViewers()
        bounds = self.logic.step6CaseViewRasBounds(self._parameterNode)
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameStep6ResearchWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        bounds = self.logic.step6ResearchWorkspaceRasBounds(
            self.logic.robotModelNodes(),
            self.logic.draftPhantomModelNodes(),
        )
        if bounds is None:
            return
        self._frameRasBoundsInViews(bounds)

    def onFrameRobot(self, checked: bool = False) -> None:
        del checked
        self.onFrameStep6ResearchWorkspace()

    def onDeleteRobotSetup(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the simulation-only robot meshes, link transforms, base "
                "transform, and mount plane from this scene?"
            ),
            windowTitle=_("Delete Step 6 robot setup"),
        ):
            return
        if self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        ):
            disconnect_dentobot_motion_control(self.logic.robotModelNodes())
        removed = self.logic.deleteRobotPlacement(
            self._parameterNode.robotBaseTransform,
            self._parameterNode.robotMountPlane,
        )
        wasModifying = self._parameterNode.StartModify()
        try:
            self._parameterNode.robotBaseTransform = None
            self._parameterNode.robotMountPlane = None
            self._parameterNode.robotKeyboardNudgeEnabled = False
        finally:
            self._parameterNode.EndModify(wasModifying)
        self._clearRobotPlacement()
        logging.info("Deleted %d Step 6 robot placement nodes", len(removed))

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
        scene_prepared = bool(
            scene_kind == "phantom"
            or (scene_kind == "case" and not case_jaw_issues)
        )
        robot_present = self._step6RobotPresent()
        local_robot_present = bool(self.logic.robotModelNodes()) if self.logic else False
        ros2_active = self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        ) if self.logic else False
        home_issues = self.logic.taskHomeFreshnessIssues(self._parameterNode) if self.logic else ()
        home_ready = not home_issues
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
        if locked:
            mount_status = _("Base placement: %1 (simulation review only).").replace(
                "%1", base_state
            )
        elif base_state == BasePlacementStatus.STALE.value:
            mount_status = _("Base placement is Stale; review and provisionally lock it again.")
        elif not scene_active:
            mount_status = _("Choose a scene before loading the robot.")
        elif not scene_prepared:
            mount_status = _("Complete the required case mouth opening in 6.0A.")
        elif not robot_present:
            mount_status = _("Load the ROS robot (or MRML fallback) before placing.")
        else:
            mount_status = _("Base mount is unlocked.")

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
            robot_present and scene_prepared
        )
        self.ui.step6WorkspaceGroupBox.enabled = robot_present and scene_prepared
        self.ui.step6TrajectoryPlanningGroupBox.enabled = (
            locked and imported and scene_prepared
        )

        place_enabled = scene_prepared and robot_present and not locked
        self.ui.lockRobotBaseMountButton.enabled = (
            scene_prepared and robot_present and not locked
        )
        self.ui.unlockRobotBaseMountButton.enabled = locked
        self.ui.planTrajectoryMotionButton.enabled = (
            imported and locked and scene_prepared
        )
        self.ui.previewTrajectoryMotionButton.enabled = has_plan
        self.ui.stopTrajectoryMotionButton.enabled = (
            self._step6MotionPreviewTimer is not None
            or bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.previewActive
            )
        )

        self.ui.connectRos2MotionButton.enabled = bool(
            scene_prepared
            and local_robot_present
            and locked
            and home_ready
            and assisted_reviewed
            and not ros2_active
        )
        self.ui.disconnectRos2MotionButton.enabled = ros2_active
        self.ui.loadRobotModelButton.enabled = scene_prepared and not locked
        self.ui.frameRobotButton.enabled = scene_prepared
        self.ui.importStep6PlanningContextButton.enabled = not locked
        self.ui.loadDraftPhantomButton.enabled = not locked

        for widget_name in (
            "createRobotMountPlaneButton",
            "flipRobotMountPlaneButton",
            "snapRobotBaseToPlaneButton",
            "resetRobotBaseButton",
        ):
            widget = getattr(self.ui, widget_name, None)
            if widget is not None:
                widget.setEnabled(place_enabled)
        self.ui.snapRobotBaseToPlaneButton.enabled = (
            place_enabled
            and self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            )
            and self.logic.isRobotMountPlaneNode(self._parameterNode.robotMountPlane)
        )
        self.ui.flipRobotMountPlaneButton.enabled = (
            place_enabled
            and self.logic.isRobotMountPlaneNode(self._parameterNode.robotMountPlane)
        )
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
        self.ui.resetRobotJointsButton.enabled = robot_present and scene_prepared
        self.ui.deleteRobotSetupButton.enabled = robot_present and not locked
        self.ui.applyTaskJointLimitsButton.enabled = robot_present and scene_prepared
        self.ui.resetTaskJointLimitsButton.enabled = robot_present and scene_prepared
        self.ui.generateRobotWorkspaceButton.enabled = (
            scene_prepared and robot_present and locked and home_ready
            and self.logic.isRobotBaseTransformNode(
                self._parameterNode.robotBaseTransform
            )
        )
        self.ui.clearRobotWorkspaceButton.enabled = bool(
            self.logic.robotWorkspaceModelNode()
        )

        panel = self._robotSimulationPanel
        if panel is not None:
            panel.loadFallbackButton.enabled = scene_prepared and not locked
            panel.enableCbctRenderingButton.enabled = imported and scene_prepared
            panel.createProxyButton.enabled = bool(
                self.logic.isRobotMountPlaneNode(self._parameterNode.robotMountPlane)
                and not locked
            )
            panel.saveTaskHomeButton.enabled = scene_prepared and locked
            panel.applyTaskHomeButton.enabled = scene_prepared and home_ready
            panel.homeStatusLabel.text = (
                _("Task Home is current for this base and robot profile.")
                if home_ready
                else " ".join(home_issues)
            )
            panel.reviewLimitsButton.enabled = bool(
                scene_prepared
                and str(self._parameterNode.step6AssistedLimitProposalJson or "").strip()
                and not assisted_reviewed
            )
            panel.workspaceReviewStatusLabel.text = (
                _("Workspace-assisted task limits were explicitly reviewed and applied.")
                if assisted_reviewed
                else _("Generate the FK workspace, then review its proposed limits.")
            )
            runtime_ready = bool(
                scene_prepared
                and local_robot_present
                and locked
                and home_ready
                and assisted_reviewed
            )
            panel.connectButton.enabled = runtime_ready and not ros2_active
            panel.disconnectButton.enabled = ros2_active
            panel.confirmTaskButton.enabled = bool(
                imported
                and scene_prepared
                and ros2_active
                and facade_capabilities
                and facade_capabilities.planning_scene_synchronized
            )
            panel.runtimeStatusLabel.text = (
                _("Immutable task snapshot is current; phased plans are enabled.")
                if task_ready
                else " ".join(task_issues)
            )
            panel.planApproachButton.enabled = bool(task_ready and ros2_active)
            panel.previewApproachButton.enabled = bool(
                isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.APPROACH.value
            )
            approach_complete = bool(
                self._robotWorkflowFacade
                and self._robotWorkflowFacade.completedPhase == MotionPhase.APPROACH.value
            )
            panel.planDrillingButton.enabled = bool(
                task_ready and ros2_active and approach_complete
            )
            panel.previewDrillingButton.enabled = bool(
                approach_complete
                and isinstance(facade_plan, PhasePlan)
                and facade_plan.success
                and facade_plan.requested_phase == MotionPhase.DRILLING.value
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
        if self._updatingFromParameterNode or self._updatingRobotPlacementUI:
            return
        try:
            if self.logic and self._parameterNode:
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Task joint limits changed."),
                )
            self._step6MotionPlan = None
            if self._robotWorkflowFacade:
                self._robotWorkflowFacade.clearTransientState()
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
                "The Halton/FK/AABB cloud is a draft design-space estimate; MoveIt remains authoritative."
            )
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #207227;"
            self.ui.clearRobotWorkspaceButton.enabled = True
        except (RuntimeError, ValueError) as exc:
            self.ui.robotWorkspaceStatusLabel.text = str(exc)
            self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))
        finally:
            qt.QApplication.restoreOverrideCursor()

    def onClearRobotWorkspace(self, checked: bool = False) -> None:
        del checked
        if not self.logic:
            return
        self.logic.deleteRobotWorkspaceModel()
        self.ui.robotWorkspaceStatusLabel.text = _("No workspace cloud generated.")
        self.ui.robotWorkspaceStatusLabel.styleSheet = "color: #b36b00;"
        self.ui.clearRobotWorkspaceButton.enabled = False

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
