"""Extracted robot placement and ROS status methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotPlacementWidgetMixin:
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
