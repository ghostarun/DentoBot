"""Extracted robot placement and ROS status methods; public APIs remain on RobotWidgetMixin."""

from __future__ import annotations

from .runtime import *


class RobotPlacementWidgetMixin:
    def _isStep6RobotWorkflowActive(self) -> bool:
        stageEntries = self._workflowStageEntries()
        return bool(
            stageEntries
            and int(self.ui.workflowStageComboBox.currentIndex) == len(stageEntries) - 1
            and not self._isStep3BActive()
        )

    def _isStep6ManualBaseReviewActive(self) -> bool:
        return bool(
            self._isStep6RobotWorkflowActive()
            and self._robotSimulationPanel
            and self._robotSimulationPanel._activeSubstep == 1
        )

    def _robotJointPositionsSi(self) -> dict[str, float]:
        if not self._parameterNode:
            return joint_positions_si_from_display(0, 0, 0, 0, 0)
        return joint_positions_si_from_display(
            self._parameterNode.robotJoint1Deg,
            self._parameterNode.robotJoint2Mm,
            self._parameterNode.robotJoint3Deg,
            self._parameterNode.robotJoint4Mm,
            self._parameterNode.robotJoint5Deg,
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
        placementSurfaceActive = self._isOfflinePlacementSurfaceActive()
        enabled = bool(
            (self._isStep6ManualBaseReviewActive() or self._isStep3BActive())
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
        self._setRobotTransformInteractionVisible(placementSurfaceActive)

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

    def _bindManualBaseCandidateInteractionNode(self, node) -> None:
        # Handle drags change the matrix, which fires TransformModifiedEvent
        # only; observing ModifiedEvent left the staged candidate unchanged, so
        # Accept Base committed the old pose (operator report 2026-10-04).
        event = slicer.vtkMRMLTransformNode.TransformModifiedEvent
        current = getattr(self, "_manualBaseCandidateInteractionNode", None)
        if current is node:
            return
        if current is not None:
            self.removeObserver(current, event,
                                self._onManualBaseCandidateInteractionModified)
        self._manualBaseCandidateInteractionNode = node
        if node is not None:
            self.addObserver(
                node,
                event,
                self._onManualBaseCandidateInteractionModified,
            )

    def _onManualBaseCandidateInteractionModified(self, caller=None, event=None) -> None:
        del event
        if (
            caller is None
            or caller is not getattr(self, "_manualBaseCandidateInteractionNode", None)
            or getattr(self, "_updatingManualBaseCandidateFromViewport", False)
            or not self._isStep6ManualBaseReviewActive()
            or not self._parameterNode
            or self._parameterNode.robotBaseMountLocked
            or not self._robotWorkflowFacade
        ):
            return
        matrix = vtk.vtkMatrix4x4()
        message = "viewport candidate update failed"
        try:
            caller.GetMatrixTransformToWorld(matrix)
            values = tuple(
                float(matrix.GetElement(row, column))
                for row in range(4)
                for column in range(4)
            )
            if not all(math.isfinite(value) for value in values):
                raise ValueError("candidate transform contains non-finite values")
            self._updatingManualBaseCandidateFromViewport = True
            result = self._robotWorkflowFacade.stageManualBaseReview(values)
        except (AttributeError, RuntimeError, TypeError, ValueError) as exc:
            result = None
            message = str(exc) or "viewport candidate update failed"
        finally:
            self._updatingManualBaseCandidateFromViewport = False
        panel = getattr(self, "_robotSimulationPanel", None)
        if result is not None and result.success:
            # The dragged ghost already shows the new candidate; re-key its cache
            # so the next refresh does not rebuild it under the active drag.
            key = getattr(self, "_manualBaseCandidateGhostKey", None)
            staged = (getattr(result, "details", {}) or {}).get("candidateMatrixWorldRasMm")
            self._manualBaseCandidateGhostKey = (
                (tuple(float(value) for value in staged),) + tuple(key[1:])
                if key and staged else None
            )
            if panel is not None:
                panel.setBaseInteractionStatus(
                    "ok",
                    "Base unlocked · viewport drag active on the detached candidate.",
                )
                panel.manualBaseReviewStatusLabel.text = (
                    "Detached Base candidate updated from the viewport. "
                    "The accepted Base is unchanged until Accept Base."
                )
        elif panel is not None:
            panel.setBaseInteractionStatus(
                "error",
                "Base unlocked · drag update rejected: "
                + str(getattr(result, "message", "") or message),
            )

    def _setRobotTransformInteractionVisible(self, visible: bool) -> None:
        if not self.logic:
            return
        robotStageActive = self._isStep6RobotWorkflowActive()
        manualReviewActive = self._isStep6ManualBaseReviewActive()
        baseTransform = (
            self._parameterNode.robotBaseTransform if self._parameterNode else None
        )
        planeNode = self._parameterNode.robotMountPlane if self._parameterNode else None
        if self.logic.isRobotBaseTransformNode(baseTransform):
            baseTransform.CreateDefaultDisplayNodes()
            displayNode = baseTransform.GetDisplayNode()
            if displayNode:
                editable = bool(
                    visible
                    and not robotStageActive
                    and self._parameterNode
                    and not self._parameterNode.robotBaseMountLocked
                )
                for methodName, value in (
                    ("SetEditorVisibility", editable),
                    ("SetHandlesInteractive", editable),
                    ("SetTranslationHandleVisibility", editable),
                    ("SetRotationHandleVisibility", editable),
                    ("SetScaleHandleVisibility", False),
                ):
                    method = getattr(displayNode, methodName, None)
                    if method:
                        method(value)
        candidate_enabled = False
        candidate_message = ""
        acceptance_unknown = False
        if robotStageActive and manualReviewActive and self._robotWorkflowFacade:
            review = self._robotWorkflowFacade.manualBaseReview()
            details = getattr(review, "details", {}) or {}
            acceptance_unknown = bool(
                str(details.get("acceptanceStatus") or "") == "unknown"
                or details.get("acceptanceUncertainty")
            )
            candidate_enabled = bool(
                visible
                and self._parameterNode
                and not self._parameterNode.robotBaseMountLocked
                and review.success
                and details.get("staged") is True
                and str(details.get("identityStatus") or "unknown") == "current"
                and not acceptance_unknown
            )
        interaction = getattr(
            self.logic, "setManualBaseCandidateInteractionEnabled", None
        )
        if callable(interaction):
            available, candidate_message = interaction(candidate_enabled)
        else:
            available = False
            candidate_message = "candidate interaction API is unavailable"
        panel = getattr(self, "_robotSimulationPanel", None)
        if panel is not None and robotStageActive and manualReviewActive:
            if acceptance_unknown:
                panel.setBaseInteractionStatus(
                    "error",
                    "Base outcome uncertain · drag blocked · Reconcile Base State.",
                )
            elif self._parameterNode and self._parameterNode.robotBaseMountLocked:
                panel.setBaseInteractionStatus(
                    "ok", "Base locked · viewport drag off."
                )
            elif candidate_enabled and available:
                panel.setBaseInteractionStatus(
                    "ok",
                    "Base unlocked · viewport drag active on the detached candidate.",
                )
            else:
                panel.setBaseInteractionStatus(
                    "blocked",
                    "Base unlocked · drag unavailable: "
                    + str(candidate_message or "stage a current Base candidate"),
                )
        if self.logic.isRobotMountPlaneNode(planeNode):
            planeNode.CreateDefaultDisplayNodes()
            displayNode = planeNode.GetDisplayNode()
            if displayNode:
                displayNode.SetHandlesInteractive(False)
                displayNode.SetTranslationHandleVisibility(False)
                displayNode.SetRotationHandleVisibility(False)
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

    def _setupSpindleGuideContactAdvancedOption(self) -> None:
        """Step 4C advanced option mirroring the 6.3 checkbox (one shared setting)."""
        container = getattr(self.ui, "targetDockingCollapsibleButton", None)
        if container is None or getattr(self, "_step4SpindleGuideContactCheckBox", None):
            return
        group = qt.QGroupBox(_("Advanced options"), container)
        layout = qt.QVBoxLayout(group)
        box = qt.QCheckBox(_("Allow spindle-housing contact with template (\u2264 0.5 mm)"), group)
        box.objectName = "DENTOBOTAllowSpindleGuideContact4C"
        box.toolTip = _(
            "Off (default): the spindle housing may not touch the template; drilling is "
            "truncated at the last collision-free state. On: up to 0.5 mm contact is "
            "tolerated as a warning. Shared with the Step 6.3 advanced option."
        )
        layout.addWidget(box)
        container.layout().addWidget(group)
        box.connect("toggled(bool)", self._onSetSpindleGuideContact)
        self._step4SpindleGuideContactCheckBox = box

    def _onSetSpindleGuideContact(self, checked: bool) -> None:
        """Store the shared advanced option and keep both checkboxes in sync."""
        if not self._parameterNode:
            return
        checked = bool(checked)
        if bool(self._parameterNode.step6AllowSpindleGuideContact) != checked:
            self._parameterNode.step6AllowSpindleGuideContact = checked
            if self.logic:
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Spindle/template contact tolerance changed; re-plan."),
                )
        boxes = [getattr(self, "_step4SpindleGuideContactCheckBox", None)]
        panel = getattr(self, "_robotSimulationPanel", None)
        if panel is not None:
            boxes.append(getattr(panel, "allowSpindleGuideContactCheckBox", None))
        for box in boxes:
            if box is not None and bool(box.checked) != checked:
                was = box.blockSignals(True)
                box.checked = checked
                box.blockSignals(was)

    def _onSetMouthBarrierEdgeMode(self, mode: str) -> None:
        """Store the 6.3 mouth-barrier edge mode and keep the combo box in sync."""
        if not self._parameterNode:
            return
        mode = str(mode or "gum_line")
        if mode not in ("gum_line", "biting_edge", "off"):
            mode = "gum_line"
        if str(self._parameterNode.step6MouthBarrierEdgeMode or "gum_line") != mode:
            self._parameterNode.step6MouthBarrierEdgeMode = mode
            if self.logic:
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Mouth barrier edges changed; re-plan."),
                )
        panel = getattr(self, "_robotSimulationPanel", None)
        box = getattr(panel, "mouthBarrierEdgeModeComboBox", None) if panel is not None else None
        if box is not None:
            index = box.findData(mode)
            if index >= 0 and int(box.currentIndex) != index:
                was = box.blockSignals(True)
                box.currentIndex = index
                box.blockSignals(was)

    def _setupReachEnvelopeOption(self) -> None:
        """6.3 Workspace: show/hide the reach envelope next to Generate Workspace."""
        label = getattr(self.ui, "robotWorkspaceStatusLabel", None)
        parent = label.parentWidget() if label is not None else None
        if parent is None or parent.layout() is None or getattr(self, "_showReachEnvelopeCheckBox", None):
            return
        box = qt.QCheckBox(_("Show reach envelope"), parent)
        box.objectName = "DENTOBOTShowReachEnvelope63"
        box.checked = True
        box.toolTip = _(
            "Show or hide the see-through envelope around the reachable drill-tip "
            "samples and the green Home-connected samples. Display only."
        )
        parent.layout().addWidget(box)
        box.connect("toggled(bool)", self._onSetShowReachEnvelope)
        self._showReachEnvelopeCheckBox = box

    @staticmethod
    def _syncCheckBox(box, checked: bool) -> None:
        if box is not None and bool(box.checked) != checked:
            was = box.blockSignals(True)
            box.checked = checked
            box.blockSignals(was)

    def _onSetShowMouthBarrier(self, checked: bool) -> None:
        """Display-only toggle for the 3D mouth barrier model."""
        if not self._parameterNode:
            return
        checked = bool(checked)
        if bool(self._parameterNode.step6ShowMouthBarrier) != checked:
            self._parameterNode.step6ShowMouthBarrier = checked
        if self.logic:
            self.logic.setStep6MouthBarrierVisible(checked, bool(self._parameterNode.step6ShowMouthBarrierSurface))
        panel = getattr(self, "_robotSimulationPanel", None)
        self._syncCheckBox(getattr(panel, "showMouthBarrierCheckBox", None) if panel is not None else None, checked)

    def _onSetShowMouthBarrierSurface(self, checked: bool) -> None:
        """Optional display of the full lip slab and cheek walls (off by default)."""
        if not self._parameterNode:
            return
        checked = bool(checked)
        if bool(self._parameterNode.step6ShowMouthBarrierSurface) != checked:
            self._parameterNode.step6ShowMouthBarrierSurface = checked
        if self.logic:
            self.logic.setStep6MouthBarrierVisible(bool(self._parameterNode.step6ShowMouthBarrier), checked)
        panel = getattr(self, "_robotSimulationPanel", None)
        self._syncCheckBox(getattr(panel, "showMouthBarrierSurfaceCheckBox", None) if panel is not None else None,
                           checked)

    def _onSetMouthBarrierOpacity(self, opacity: float) -> None:
        """Display-only opacity of the optional full barrier surface (default 0.12)."""
        if not self._parameterNode:
            return
        opacity = min(1.0, max(0.0, float(opacity)))
        if abs(float(self._parameterNode.step6MouthBarrierOpacity) - opacity) > 1e-9:
            self._parameterNode.step6MouthBarrierOpacity = opacity
        if self.logic:
            self.logic.setStep6MouthBarrierOpacity(opacity)

    def _onSetDevFastMode(self, checked: bool) -> None:
        """Development-only first-Complete route mode; stamped, read at Plan Approach."""
        facade = getattr(self, "_robotWorkflowFacade", None)
        if facade is not None:
            facade._dev_first_complete_route = bool(checked)

    def _onSetDepthPeeling(self, checked: bool) -> None:
        """3D-view depth peeling; display only (operator 2026-10-03)."""
        if self.logic:
            self.logic.setStep6DepthPeeling(bool(checked))

    def _step6TaskSpaceBoxCenter(self):
        """ROI draft centre when loaded, else the current opened-incisor midpoint."""
        panel = getattr(self, "_robotSimulationPanel", None)
        if panel is not None and getattr(panel, "_taskSpaceRoiInitialized", False):
            return tuple(float(spin.value) for spin in panel.taskSpaceRoiCenterSpinBoxes)
        facade = getattr(self, "_robotWorkflowFacade", None)
        result = facade.defaultTaskSpaceRoi() if facade is not None else None
        if result is None or not result.success:
            return None
        return tuple(float(value) for value in result.payload["centerWorldRasMm"])

    def _onSetTaskSpaceBox(self, visible: bool, side_mm: float, opacity: float) -> None:
        """Optional incisor-centred task-space box; display only (operator 2026-10-03)."""
        if not self._parameterNode or not self.logic:
            return
        node = self._parameterNode
        visible, side_mm = bool(visible), float(side_mm)
        opacity = min(self.logic.TASK_SPACE_BOX_MAX_OPACITY, max(0.0, float(opacity)))
        if bool(node.step6ShowTaskSpaceBox) != visible:
            node.step6ShowTaskSpaceBox = visible
        if abs(float(node.step6TaskSpaceBoxSideMm) - side_mm) > 1e-9:
            node.step6TaskSpaceBoxSideMm = side_mm
        if abs(float(node.step6TaskSpaceBoxOpacity) - opacity) > 1e-9:
            node.step6TaskSpaceBoxOpacity = opacity
        center = self._step6TaskSpaceBoxCenter() if visible else None
        self.logic.updateStep6TaskSpaceBox(center, side_mm, opacity, visible)
        panel = getattr(self, "_robotSimulationPanel", None)
        label = getattr(panel, "taskSpaceBoxStatusLabel", None) if panel is not None else None
        if label is not None:
            label.text = (
                "" if not visible or center is not None else
                "Task-space box needs the current Case Foundation incisor midpoint."
            )

    def _onSetShowReachEnvelope(self, checked: bool) -> None:
        """Display-only toggle for the 6.3 reach envelope and Home-connected samples."""
        if not self._parameterNode:
            return
        checked = bool(checked)
        if bool(self._parameterNode.step6ShowReachEnvelope) != checked:
            self._parameterNode.step6ShowReachEnvelope = checked
        if self.logic:
            self.logic.setStep6ReachEnvelopeVisible(checked)
        self._syncCheckBox(getattr(self, "_showReachEnvelopeCheckBox", None), checked)

    def _basePlacementSearchNoteText(self) -> str:
        """Last Find Reachable Base result while lock state and Base pose are unchanged."""
        note = getattr(self, "_basePlacementSearchNote", None)
        if not note or not self._parameterNode or not self.logic:
            return ""
        message, locked, fingerprint = note
        base = self._parameterNode.robotBaseTransform
        current = str(self.logic.robotBasePoseFingerprint(base) or "") if base else ""
        if bool(self._parameterNode.robotBaseMountLocked) != locked or current != fingerprint:
            return ""
        return message

    def _showBasePlacementSearchNote(self, message: str, error: bool) -> None:
        """Keep the search result visible: the Base review refresh rewrites the label."""
        base = self._parameterNode.robotBaseTransform
        self._basePlacementSearchNote = (
            message,
            bool(self._parameterNode.robotBaseMountLocked),
            str(self.logic.robotBasePoseFingerprint(base) or "") if base else "",
        )
        self._robotSimulationPanel.manualBaseReviewStatusLabel.text = message
        self._updateStep6PlanningUi(message, error=error)

    def _onStep6SearchBasePlacement(self) -> None:
        """Run the forehead-plane IK preflight and stage the best Base for review."""
        panel = self._robotSimulationPanel
        facade = self._robotWorkflowFacade
        if not panel or not facade or not self._parameterNode or not self.logic:
            return
        locked_base = bool(self._parameterNode.robotBaseMountLocked)

        def progress(done, total):
            if done % 10 == 0:
                panel.manualBaseReviewStatusLabel.text = _(
                    "Find Reachable Base: %1 of up to %2 candidate Bases checked..."
                ).replace("%1", str(done)).replace("%2", str(total))
                slicer.app.processEvents()

        def run(**options):
            qt.QApplication.setOverrideCursor(qt.Qt.WaitCursor)
            try:
                return self.logic.searchForeheadBasePlacement(
                    self._parameterNode, progress=progress, **options)
            except (OSError, RuntimeError, ValueError) as exc:
                self._showBasePlacementSearchNote(
                    _("Base placement search failed: %1").replace("%1", str(exc)), error=True)
                return None
            finally:
                qt.QApplication.restoreOverrideCursor()

        if locked_base:
            self._showBasePlacementSearchNote(_(
                "Find Reachable Base: the Base is locked. Unlock it to search and stage, or "
                "open the level 4 ranking board to preview candidates without unlocking."
            ), error=True)
            if slicer.util.confirmYesNoDisplay(_(
                "The accepted Base is locked.\n\nOpen the level 4 ranking board to preview "
                "every valid Base as a display-only ghost (exhaustive search, about a "
                "minute)? Using one later offers to unlock."
            )):
                report = run(reference="forehead_seat", deep=True, exhaustive=True)
                if report is not None:
                    self._openBaseCandidateBoard(report)
            return
        panel.manualBaseReviewStatusLabel.text = _(
            "Find Reachable Base (level 1): searching the forehead plane (IK preflight "
            "+ mouth-barrier check)..."
        )
        slicer.app.processEvents()
        report = run()
        if report is None:
            return
        self._lastBasePlacementSearch = report
        best = report.get("best")
        if best is not None and report.get("barrier_clear", True):
            result = facade.stageManualBaseReview(tuple(best["matrix_world_ras_mm"]))
            message = _(
                "Level 1: %1 of %2 forehead-plane Bases reach the full stroke. Staged nearest "
                "that clears the mouth barrier: u=%3 mm, v=%4 mm, depth %5 mm (minimum slider "
                "margin %6 mm). Review and Accept; MoveIt checks anatomy and planning afterwards."
            ).replace("%1", str(report["feasible_count"])).replace(
                "%2", str(report["evaluated"])).replace("%3", f"{best['u_mm']:.1f}").replace(
                "%4", f"{best['v_mm']:.1f}").replace("%5", f"{best.get('depth_mm', 0.0):.1f}").replace(
                "%6", f"{best['minimum_slider_margin_mm']:.2f}")
            self._showBasePlacementSearchNote(
                str(result.message) if not result.success else message, error=not result.success)
            return
        clearance = (best or {}).get("clearance") or {}
        reason = (
            _("%1 forehead-plane Bases reach the stroke, but none clears the mouth barrier "
              "(nearest fails at %2: %3)").replace("%1", str(report["feasible_count"])).replace(
                "%2", str(clearance.get("failed"))).replace("%3", ", ".join(clearance.get("contacts") or []))
            if best is not None
            else _("no forehead-plane Base reaches the stroke (%1 checked)").replace(
                "%1", str(report.get("evaluated")))
        )
        self._showBasePlacementSearchNote(_("Level 1 failed: %1.").replace("%1", reason), error=True)
        level = self._askBaseSearchLevel(reason)
        if level == 2:
            panel.manualBaseReviewStatusLabel.text = _("Find Reachable Base (level 2): deep search...")
            slicer.app.processEvents()
            report = run(reference="current", deep=True)
            if report is None or self._stageAroundBaseResult(report, 2):
                return
            if not slicer.util.confirmYesNoDisplay(_(
                "Level 2 found no Base near the current one that reaches the stroke and "
                "clears the mouth barrier.\n\nRun level 3 (exhaustive: every valid Base "
                "around the auto placement, ranked by least movement)? It can take minutes."
            )):
                return
            level = 3
        if level in (3, 4):
            panel.manualBaseReviewStatusLabel.text = _(
                "Find Reachable Base (level %1): exhaustive search around the auto placement "
                "(about a minute)...").replace("%1", str(level))
            slicer.app.processEvents()
            report = run(reference="forehead_seat", deep=True, exhaustive=True)
            if report is None:
                return
            if level == 4:
                self._openBaseCandidateBoard(report)
            elif self._stageAroundBaseResult(report, 3) and int(report.get("clear_count") or 0) > 1:
                if slicer.util.confirmYesNoDisplay(_(
                    "Level 3 staged the least-movement Base. Open the level 4 ranking board "
                    "to compare all %1 valid Bases?").replace("%1", str(report["clear_count"]))):
                    self._openBaseCandidateBoard(report)

    def _askBaseSearchLevel(self, reason: str):
        """Operator choice after level 1 fails: 2 (fast), 3 (exhaustive) or None."""
        box = qt.QMessageBox(slicer.util.mainWindow())
        box.setWindowTitle(_("Find Reachable Base"))
        box.setText(_(
            "Level 1 failed: %1.\n\nLevel 2 moves the current Base (+-30 mm in-plane, "
            "+-20 mm depth, +-40 deg yaw) and stops at the smallest move that reaches the "
            "stroke and clears the mouth barrier. Level 3 checks the whole range around "
            "the virtual-forehead auto placement and stages the valid Base with the least "
            "movement; level 4 opens a ranking board of every valid Base to preview and "
            "choose (levels 3-4 take about a minute)."
        ).replace("%1", reason))
        level2 = box.addButton(_("Level 2 (nearest move)"), qt.QMessageBox.AcceptRole)
        level3 = box.addButton(_("Level 3 (auto: least movement)"), qt.QMessageBox.ActionRole)
        level4 = box.addButton(_("Level 4 (ranking board)"), qt.QMessageBox.ActionRole)
        box.addButton(qt.QMessageBox.Cancel)
        box.exec_()
        clicked = box.clickedButton()
        return {level2: 2, level3: 3, level4: 4}.get(clicked)

    def _openBaseCandidateBoard(self, report) -> None:
        """Level 4 (operator 2026-10-04): modeless ranking board of every valid Base.

        Selecting a row shows that Base as the cyan ghost: staged when the Base is
        unlocked, display-only when it is locked. Use keeps it staged (offering to
        unlock first); Cancel/close restores the prior state. Nothing is accepted.
        """
        candidates = list(report.get("clear_all") or [])
        facade = self._robotWorkflowFacade
        if not candidates or facade is None:
            self._showBasePlacementSearchNote(_("Level 4: no valid Base candidates to rank."), error=True)
            return
        self._lastBasePlacementSearch = report
        previous = (facade.manualBaseReview().details or {}).get("candidateMatrixWorldRasMm")
        old = getattr(self, "_baseCandidateBoard", None)
        if old is not None:
            old.close()
        dialog = qt.QDialog(slicer.util.mainWindow())
        dialog.objectName = "DENTOBOTBaseCandidateBoard"
        dialog.setWindowTitle(_("Find Reachable Base — level 4 ranking board"))
        dialog.setModal(False)
        layout = qt.QVBoxLayout(dialog)
        hint = qt.QLabel(_(
            "%1 valid Bases (reach + mouth-barrier clearance), ranked by least movement from "
            "the virtual-forehead auto placement (movement = mm/10 + yaw deg/10). Select a "
            "row to preview it as the cyan ghost; rotate the 3D view freely."
        ).replace("%1", str(len(candidates))), dialog)
        hint.wordWrap = True
        layout.addWidget(hint)
        headers = [_("Rank"), _("Depth mm"), _("u mm"), _("v mm"), _("Yaw deg"), _("Movement"),
                   _("Slider margin mm"), _("Revolute margin deg")]
        table = qt.QTableWidget(len(candidates), len(headers), dialog)
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(qt.QAbstractItemView.SelectRows)
        table.setSelectionMode(qt.QAbstractItemView.SingleSelection)
        table.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
        table.verticalHeader().setVisible(False)  # the Rank column numbers rows
        for row, record in enumerate(candidates):
            values = (str(row + 1), *(f"{float(record[key]):+.0f}" for key in
                                     ("depth_mm", "u_mm", "v_mm", "yaw_deg")),
                      f"{float(record['cost']):.2f}", f"{float(record['minimum_slider_margin_mm']):.1f}",
                      f"{float(record['minimum_revolute_margin_deg']):.1f}")
            for column, text in enumerate(values):
                table.setItem(row, column, qt.QTableWidgetItem(text))
        table.resizeColumnsToContents()
        layout.addWidget(table)
        status = qt.QLabel("", dialog)
        status.wordWrap = True
        layout.addWidget(status)
        buttons = qt.QHBoxLayout()
        use_button = qt.QPushButton(_("Use selected Base"), dialog)
        cancel_button = qt.QPushButton(_("Cancel"), dialog)
        buttons.addWidget(use_button)
        buttons.addWidget(cancel_button)
        layout.addLayout(buttons)

        def describe(row):
            record = candidates[row]
            return _("rank %1: depth %2 mm, u %3 / v %4 mm, yaw %5 deg").replace(
                "%1", str(row + 1)).replace("%2", f"{record['depth_mm']:+.0f}").replace(
                "%3", f"{record['u_mm']:+.0f}").replace("%4", f"{record['v_mm']:+.0f}").replace(
                "%5", f"{record['yaw_deg']:+.0f}")

        locked = lambda: bool(self._parameterNode and self._parameterNode.robotBaseMountLocked)
        preview_only = {"shown": False}

        def clear_preview():
            if preview_only["shown"]:
                self.logic.clearManualBaseCandidateGhost()
                preview_only["shown"] = False

        def preview():
            row = table.currentRow()
            if row < 0:
                return
            matrix = tuple(candidates[row]["matrix_world_ras_mm"])
            if locked():
                # Display-only ghost: the accepted Base stays locked and nothing is staged.
                self._manualBaseCandidateGhostKey = None
                shown, reason = self.logic.showManualBaseCandidateGhost(matrix)
                preview_only["shown"] = bool(shown)
                status.text = (_("Previewing %1 (cyan ghost, display only; the accepted Base "
                                 "stays locked).").replace("%1", describe(row))
                               if shown else str(reason))
                return
            result = facade.stageManualBaseReview(matrix)
            status.text = (_("Previewing %1 (cyan ghost).").replace("%1", describe(row))
                           if result.success else str(result.message))
            self._updateStep6PlanningUi(status.text, error=not result.success)

        def use():
            row = table.currentRow()
            if row < 0:
                dialog.close()
                return
            if locked():
                if not slicer.util.confirmYesNoDisplay(_(
                    "Unlock the accepted Base and stage %1 for Review/Accept? Unlocking makes "
                    "the current Task Home, workspace and task validation stale."
                ).replace("%1", describe(row))):
                    return
                clear_preview()
                self.onUnlockRobotBaseMount()
                if locked():
                    return
                result = facade.stageManualBaseReview(tuple(candidates[row]["matrix_world_ras_mm"]))
                self._updateStep6PlanningUi(str(result.message), error=not result.success)
                if not result.success:
                    status.text = str(result.message)
                    return
            self._showBasePlacementSearchNote(_(
                "Level 4: staged %1 of %2 valid Bases. Review and Accept; MoveIt then "
                "checks anatomy, template and planning."
            ).replace("%1", describe(row)).replace("%2", str(len(candidates))), error=False)
            dialog.close()

        def cancel():
            if preview_only["shown"]:
                clear_preview()
            elif previous:
                facade.stageManualBaseReview(tuple(previous))
            self._updateStep6PlanningUi(_("Level 4 ranking board cancelled; previous state restored."))
            dialog.close()

        table.itemSelectionChanged.connect(preview)
        use_button.clicked.connect(lambda _checked=False: use())
        cancel_button.clicked.connect(lambda _checked=False: cancel())
        dialog.finished.connect(lambda _result=0: clear_preview())  # window X also removes it
        self._baseCandidateBoard = dialog
        dialog.resize(760, 420)
        dialog.show()
        table.selectRow(0)

    def _stageAroundBaseResult(self, report, level: int) -> bool:
        """Stage the best level 2/3 Base with a move description; False when none."""
        self._lastBasePlacementSearch = report
        best = report.get("best")
        origin = _("the current Base") if level == 2 else _("the auto placement")
        counts = _("%1 checked, %2 reachable, %3 clear").replace("%1", str(report.get("evaluated"))).replace(
            "%2", str(report.get("feasible_count"))).replace("%3", str(report.get("clear_count")))
        if best is None:
            centre = (report.get("centre") or {}).get("clearance") or {}
            self._showBasePlacementSearchNote(_(
                "Level %1: no Base within +-30 mm in-plane, +-20 mm depth and +-40 deg yaw "
                "of %2 both reaches the stroke and clears the mouth barrier (%3). Reference "
                "Base: %4."
            ).replace("%1", str(level)).replace("%2", origin).replace("%3", counts).replace(
                "%4", (str(centre.get("failed")) + " " + ", ".join(centre.get("contacts") or []))
                if centre else _("stroke not reachable")), error=True)
            return False
        move = lambda r: _("depth %1 mm, u %2 / v %3 mm, yaw %4 deg").replace(
            "%1", f"{r['depth_mm']:+.0f}").replace("%2", f"{r['u_mm']:+.0f}").replace(
            "%3", f"{r['v_mm']:+.0f}").replace("%4", f"{r['yaw_deg']:+.0f}")
        result = self._robotWorkflowFacade.stageManualBaseReview(tuple(best["matrix_world_ras_mm"]))
        message = _(
            "Level %1 staged: %2 from %3 (%4). Stroke reachable (slider margin %5 mm, "
            "revolute %6 deg); start, Home and PreEntry poses and their straight paths "
            "clear the mouth barrier. Review and Accept; MoveIt then checks anatomy, "
            "template and planning."
        ).replace("%1", str(level)).replace("%2", move(best)).replace("%3", origin).replace(
            "%4", counts).replace("%5", f"{best['minimum_slider_margin_mm']:.1f}").replace(
            "%6", f"{best['minimum_revolute_margin_deg']:.1f}")
        if level == 3:
            message += _(" Ranked by least movement: ") + "; ".join(
                f"{index}) " + move(record) for index, record in
                enumerate(report.get("ranked", [])[:5], start=1)) + "."
        self._showBasePlacementSearchNote(
            str(result.message) if not result.success else message, error=not result.success)
        return True

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
            # Accept/Reconcile Base moves and locks the Base itself and verifies
            # the result; do not treat that sanctioned move as an operator edit
            # (which would unreview and unlock the Base mid-acceptance).
            acceptanceOwnsChange = bool(
                getattr(self._robotWorkflowFacade, "manualBaseAcceptanceInProgress", False)
            )
            if (
                self._lastRobotBasePoseFingerprint
                and poseFingerprint != self._lastRobotBasePoseFingerprint
                and not acceptanceOwnsChange
            ):
                caller.SetAttribute(
                    self.logic.ROBOT_BASE_PLACEMENT_AUTHORITY_ATTRIBUTE,
                    self.logic.ROBOT_BASE_MANUAL_UNREVIEWED_AUTHORITY,
                )
                caller.SetAttribute("DENTOBOT.PlacementWarning", None)
                wasLocked = bool(self._parameterNode.robotBaseMountLocked)
                if not wasLocked:
                    self.logic.issueStep6BasePlacementRevision(self._parameterNode)
                self.logic.invalidateStep6TaskConfirmation(
                    self._parameterNode,
                    _("Robot base pose changed."),
                    makeBaseStale=wasLocked,
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
        self._onSetSpindleGuideContact(bool(self._parameterNode.step6AllowSpindleGuideContact))
        self._onSetMouthBarrierEdgeMode(str(self._parameterNode.step6MouthBarrierEdgeMode or "gum_line"))
        panel = getattr(self, "_robotSimulationPanel", None)
        self._syncCheckBox(getattr(panel, "showMouthBarrierCheckBox", None) if panel is not None else None,
                           bool(self._parameterNode.step6ShowMouthBarrier))
        self._syncCheckBox(getattr(panel, "showMouthBarrierSurfaceCheckBox", None) if panel is not None else None,
                           bool(self._parameterNode.step6ShowMouthBarrierSurface))
        self._syncCheckBox(getattr(self, "_showReachEnvelopeCheckBox", None),
                           bool(self._parameterNode.step6ShowReachEnvelope))
        if panel is not None and hasattr(panel, "syncStep6OverlayControls"):
            panel.syncStep6OverlayControls(
                barrier_opacity=float(self._parameterNode.step6MouthBarrierOpacity),
                show_task_space_box=bool(self._parameterNode.step6ShowTaskSpaceBox),
                task_space_box_side_mm=float(self._parameterNode.step6TaskSpaceBoxSideMm),
                task_space_box_opacity=float(self._parameterNode.step6TaskSpaceBoxOpacity),
            )
        if panel is not None and hasattr(panel, "syncStep6RunOptions"):
            facade = getattr(self, "_robotWorkflowFacade", None)
            panel.syncStep6RunOptions(
                dev_fast_mode=bool(getattr(facade, "_dev_first_complete_route", False)),
                depth_peeling=self.logic.step6DepthPeelingEnabled(),
            )
        # Recreate only a missing model (not saved with the scene). A box hidden by the
        # active view preset stays hidden; re-showing it here popped it up at random
        # points in Step 6 (operator 2026-10-04).
        if bool(self._parameterNode.step6ShowTaskSpaceBox) and not self.logic.step6TaskSpaceBoxExists():
            self._onSetTaskSpaceBox(True, float(self._parameterNode.step6TaskSpaceBoxSideMm),
                                    float(self._parameterNode.step6TaskSpaceBoxOpacity))
        baseTransform = self._parameterNode.robotBaseTransform
        modelCount = len(self.logic.robotModelNodes())
        if message:
            status = message
            style = "color: #207227;"
        elif self.logic.isRos2MotionControlActive(baseTransform):
            status = _("ROS robot is in the viewport. Place the mount, then lock.")
            style = "color: #207227;"
        elif not self.logic.isRobotBaseTransformNode(baseTransform) or modelCount != 7:
            status = _("Complete the Case Foundation, then load the offline robot in Step 3B (mirrored in 6.1A).")
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
        self._updateOfflinePlacementMirrorStatus()

    def _updateRobotPlacement(self) -> None:
        if not self._parameterNode or not self.logic or not hasattr(self, "ui"):
            return
        quarantineMessage = self.logic.quarantineLegacyRobotBasePlacement(
            self._parameterNode
        )
        if quarantineMessage:
            logging.warning(quarantineMessage)
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
        placementSurfaceActive = self._isOfflinePlacementSurfaceActive()
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
            # The legacy plane was derived from the base itself.  It remains
            # inspectable, but cannot provide independent placement evidence.
            self.ui.createRobotMountPlaneButton.enabled = False
            self.ui.snapRobotBaseToPlaneButton.enabled = False
            self.ui.flipRobotMountPlaneButton.enabled = False
            self.ui.robotMountPlaneSelector.enabled = False
            self.ui.robotKeyboardNudgeCheckBox.enabled = baseValid
            self.ui.frameRobotButton.enabled = bool(modelCount)
        finally:
            self._updatingRobotPlacementUI = False
        self._updateRobotPlacementStatus()
        self._updateStep6CaseJawOpeningControls()
        self._updateStep6CaseJawOpeningStatus()
        self._updateRos2MotionControlStatus()
        self._updateRobotKeyboardShortcutState()
        if self._parameterNode and self.logic:
            self.logic._applyRobotBaseMountInteractionState(
                self._parameterNode,
                bool(self._parameterNode.robotBaseMountLocked),
            )
            self._setRobotTransformInteractionVisible(
                self._isOfflinePlacementSurfaceActive()
            )
            try:
                self._applyTaskJointLimitsToJointSpinboxes()
            except ValueError:
                pass
        self._updateStep6PlanningUi()
        if robotStageActive or placementSurfaceActive:
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
            lowered = message.lower()
            style = (
                "color: #c62828;"
                if "failed" in lowered
                else "color: #b36b00;"
                if "remediation" in lowered
                else "color: #207227;"
            )
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

    def _updateOfflinePlacementMirrorStatus(self) -> None:
        label = getattr(self, "_step61PlacementMirrorStatusLabel", None)
        if label is None or not self._parameterNode or not self.logic:
            return
        try:
            payload = self.logic.offlinePlacementMirrorState(self._parameterNode)
        except (AttributeError, RuntimeError, TypeError, ValueError):
            return
        state = str(payload.get("state") or "missing")
        if state == "pass":
            text = _(
                "PASS — Step 3B virtual-forehead auto-placement is current "
                "(7-link robot, matching Case Foundation fingerprint). "
                "Forehead plane is shown. Manual nudge/lock remain available."
            )
            style = "color: #207227; font-weight: 600;"
        elif state == "manual":
            text = _(
                "Placement present (manual adjustment). Auto-PASS requires an "
                "unmodified VirtualForeheadPriorV1 that still matches the "
                "Case Foundation. Nudge, review, and lock remain available."
            )
            style = "color: #207227;"
        else:
            text = _(
                "Offline base auto-placement is not current. Complete it in "
                "Step 3B (Propose virtual forehead + base). This 6.1 mirror "
                "does not create a second robot."
            )
            style = "color: #b36b00; font-weight: 600;"
        label.text = text
        label.styleSheet = style
        if self._step3BContinueButton is not None:
            pose_ok = bool(payload.get("poseEligible"))
            self._step3BContinueButton.enabled = pose_ok

    def onConnectRos2MotionControl(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic or not self._robotWorkflowFacade:
            return
        from .workflow_progress import WorkflowProgress

        progress = WorkflowProgress("Step 6.1 connect ROS 2")
        try:
            progress.update("Connecting ROS 2 motion control", can_cancel=False)
            wasSuppressingParameterRefresh = getattr(
                self, "_suppressParameterRefreshDuringRobotConnect", False
            )
            self._suppressParameterRefreshDuringRobotConnect = True
            try:
                result = self._robotWorkflowFacade.connect(
                    open_motion_module=False,
                    progress=lambda phase, done=None, total=None: progress.update(
                        phase, done, total, can_cancel=False
                    ),
                )
            finally:
                self._suppressParameterRefreshDuringRobotConnect = (
                    wasSuppressingParameterRefresh
                )
            if result.success or result.details.get("runtimeConnected", False):
                progress.update("Refreshing connected workflow", can_cancel=False)
                self._updateRobotPlacement()
                self._applyStep6RecommendedView()
        finally:
            progress.close()
        if not result.success:
            if result.details.get("runtimeConnected", False):
                self._updateRos2MotionControlStatus(
                    _("ROS 2 connected for Task Home remediation: %1").replace(
                        "%1", result.message
                    )
                )
                slicer.util.warningDisplay(result.message)
                return
            self._updateRos2MotionControlStatus(
                _("ROS 2 connect failed: %1").replace("%1", result.message)
            )
            slicer.util.errorDisplay(result.message)
            return
        self._updateRos2MotionControlStatus(result.message)

    def onDisconnectRos2MotionControl(self, checked: bool = False) -> None:
        del checked
        if not self.logic or not self._robotWorkflowFacade:
            return
        from .workflow_progress import WorkflowProgress

        progress = WorkflowProgress("Step 6.1 disconnect ROS 2")
        try:
            result = self._robotWorkflowFacade.disconnect(
                progress=lambda phase, done=None, total=None: progress.update(
                    phase, done, total, can_cancel=False
                )
            )
            if result.success:
                progress.update("Refreshing disconnected workflow", can_cancel=False)
                self._updateRobotPlacement()
        finally:
            progress.close()
        if not result.success:
            self._updateRos2MotionControlStatus(
                _("ROS 2 disconnect failed: %1").replace("%1", result.message)
            )
            slicer.util.errorDisplay(result.message)
            return
        self._updateRos2MotionControlStatus(result.message)
