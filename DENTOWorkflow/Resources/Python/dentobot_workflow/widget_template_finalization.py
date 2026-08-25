"""Extracted template finalization methods; public APIs remain on GuideBuildWidgetMixin."""

from __future__ import annotations

from .runtime import *


class TemplateFinalizationWidgetMixin:
    def _clearTemplateFinalization(self) -> None:
        if not hasattr(self, "ui"):
            return
        self._bindTemplateFinalizationEditNodes(None, None)
        self._updatingTemplateFinalizationUI = True
        try:
            self.ui.finalVerificationModelSelector.setCurrentNode(None)
            self.ui.finalVerificationTreeWidget.clear()
            self.ui.verifyFinalTemplateButton.enabled = False
            self.ui.showFinalTemplateButton.enabled = False
            self.ui.exportFinalTemplateButton.enabled = False
            self.ui.finalVerificationStatusLabel.text = _(
                "Generate the integrated Step 5B unified template first."
            )
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #b36b00;"
            self.ui.templateFinalizationSourceValueLabel.text = _("--")
            self.ui.templateTrimPlaneSelector.setCurrentNode(None)
            self.ui.templateTrimCurveSelector.setCurrentNode(None)
            self.ui.finalizedTemplateShellModelSelector.setCurrentNode(None)
            self._updateLineageBadge(
                self.ui.templateFinalizationLineageLabel,
                None,
                _("Step 4A → Step 4B → Step 4C → Step 5A → Step 5B → Step 5C"),
                _("Inherited lineage: waiting for a current Step 5B shell."),
            )
            for button in (
                self.ui.continueTemplateFinalizationButton,
                self.ui.createTemplateTrimPlaneButton,
                self.ui.placeTemplateTrimCurveButton,
                self.ui.applyTemplateFinalizationButton,
                self.ui.openDynamicModelerButton,
                self.ui.deleteTemplateFinalizationButton,
                self.ui.exportResearchTemplateButton,
            ):
                button.enabled = False
            self.ui.restoreTemplateFinalizationViewButton.enabled = bool(
                self._templateFinalizationViewIsolated()
            )
            self._updateTemplateFinalizationCameraFrameLabel()
            self.ui.templateFinalizationStatusLabel.text = _(
                "Generate a current Step 5B shell and sleeve first."
            )
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #b36b00;"
        finally:
            self._updatingTemplateFinalizationUI = False

    @staticmethod
    def _templateFinalizationModeFromIndex(index: int) -> str:
        return "CurveCut" if int(index) == 1 else "PlaneCut"

    @staticmethod
    def _templateFinalizationKeepChoices(mode: str) -> tuple[tuple[str, str], ...]:
        if mode == "CurveCut":
            return (
                (_("Inside closed curve"), "Inside"),
                (_("Outside closed curve"), "Outside"),
            )
        return (
            (_("Below ROI-horizontal plane (ROI −Z side)"), "Negative"),
            (_("Above ROI-horizontal plane (ROI +Z side)"), "Positive"),
        )

    def _setTemplateFinalizationKeepChoices(self, mode: str, selected: str) -> None:
        comboBox = self.ui.templateFinalizationKeepRegionComboBox
        choices = self._templateFinalizationKeepChoices(mode)
        validValues = {value for _label, value in choices}
        if selected not in validValues:
            selected = choices[0][1]
            if self._parameterNode:
                self._parameterNode.templateFinalizationKeepRegion = selected
        comboBox.clear()
        selectedIndex = 0
        for index, (label, value) in enumerate(choices):
            comboBox.addItem(label, value)
            if value == selected:
                selectedIndex = index
        comboBox.setCurrentIndex(selectedIndex)

    def _bindTemplateFinalizationEditNodes(self, planeNode, curveNode) -> None:
        if self._templateTrimPlaneNode is not planeNode:
            if self._templateTrimPlaneNode:
                self.removeObserver(
                    self._templateTrimPlaneNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimPlaneModified,
                )
            self._templateTrimPlaneNode = planeNode
            if planeNode:
                self.addObserver(
                    planeNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimPlaneModified,
                )
        if self._templateTrimCurveNode is not curveNode:
            if self._templateTrimCurveNode:
                self.removeObserver(
                    self._templateTrimCurveNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimCurveModified,
                )
            self._templateTrimCurveNode = curveNode
            if curveNode:
                self.addObserver(
                    curveNode,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateTrimCurveModified,
                )

    def _onTemplateTrimPlaneModified(self, caller=None, event=None) -> None:
        del event
        if (
            self._restoringTemplateTrimPlane
            or not self._parameterNode
            or caller is not self._parameterNode.templateTrimPlane
        ):
            return
        if caller.GetNumberOfDefinedControlPoints() >= 1:
            self._enforceTemplateTrimPlaneOrientation()
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C trim plane changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateFinalization)

    def _onTemplateTrimCurveModified(self, caller=None, event=None) -> None:
        del event
        if not self._parameterNode or caller is not self._parameterNode.templateTrimCurve:
            return
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C margin curve changed."),
        )
        qt.QTimer.singleShot(0, self._updateTemplateFinalization)

    def _updateTemplateFinalization(self) -> None:
        """Update the active Step 5C verification and single-export gate."""

        if self._updatingTemplateFinalizationUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateFinalization()
            return
        finalModel = self._parameterNode.finalPrintableTemplateModel
        self._updatingTemplateFinalizationUI = True
        try:
            if self.ui.finalVerificationModelSelector.currentNode() is not finalModel:
                self.ui.finalVerificationModelSelector.setCurrentNode(finalModel)
            self.ui.finalVerificationTreeWidget.clear()
            self.ui.verifyFinalTemplateButton.enabled = False
            self.ui.showFinalTemplateButton.enabled = bool(
                self.logic.isFinalPrintableTemplateModelNode(finalModel)
            )
            self.ui.exportFinalTemplateButton.enabled = False
        finally:
            self._updatingTemplateFinalizationUI = False

        if not finalModel:
            self.ui.finalVerificationStatusLabel.text = _(
                "Generate the integrated Step 5B unified template first."
            )
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #b36b00;"
            return
        try:
            summary = self.logic.getFinalPrintableTemplateSummary(finalModel)
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self.ui.finalVerificationStatusLabel.text = str(exc)
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #b00020;"
            return

        verification = summary["verification"]
        checks = verification.get("checks", []) if isinstance(verification, dict) else []
        for check in checks:
            item = qt.QTreeWidgetItem()
            item.setText(0, str(check.get("result", "--")))
            item.setText(1, str(check.get("name", "")))
            item.setText(2, str(check.get("details", "")))
            result = str(check.get("result", ""))
            color = (
                qt.QColor("#b00020")
                if result == "FAIL"
                else qt.QColor("#b36b00")
                if result == "WARNING"
                else qt.QColor("#207227")
            )
            item.setForeground(0, qt.QBrush(color))
            self.ui.finalVerificationTreeWidget.addTopLevelItem(item)
        self.ui.finalVerificationTreeWidget.resizeColumnToContents(0)
        self.ui.finalVerificationTreeWidget.resizeColumnToContents(1)

        current = summary["geometryState"] == "Current"
        verifiedCurrent = bool(
            current
            and summary["verificationState"] in {"PASS", "WARNING"}
            and verification.get("overall") == summary["verificationState"]
            and verification.get("finalModelUpdatedUtc")
            == (finalModel.GetAttribute("DENTOBOT.UpdatedUtc") or "")
        )
        self.ui.verifyFinalTemplateButton.enabled = current
        self.ui.exportFinalTemplateButton.enabled = verifiedCurrent
        if not current:
            message = _("Final template is stale: %1").replace(
                "%1", summary["staleReason"] or _("regeneration required")
            )
            style = "color: #b00020;"
        elif summary["verificationState"] == "FAIL":
            message = _("Verification FAIL. Resolve failed checks and regenerate as required.")
            style = "color: #b00020;"
        elif verifiedCurrent:
            message = _(
                "Verification %1. One unified binary STL export is enabled."
            ).replace("%1", summary["verificationState"])
            style = (
                "color: #207227;"
                if summary["verificationState"] == "PASS"
                else "color: #b36b00;"
            )
        else:
            message = _("Run final geometry verification before STL export.")
            style = "color: #b36b00;"
        self.ui.finalVerificationStatusLabel.text = message
        self.ui.finalVerificationStatusLabel.styleSheet = style

    def onFinalVerificationModelSelectionChanged(self, modelNode) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        self._parameterNode.finalPrintableTemplateModel = modelNode
        self._updateTemplateFinalization()

    def onVerifyFinalTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            verification = self.logic.verifyFinalPrintableTemplate(
                self._parameterNode.finalPrintableTemplateModel
            )
            logging.info(
                "Step 5C verification %s with %d checks",
                verification["overall"],
                len(verification["checks"]),
            )
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            self.ui.finalVerificationStatusLabel.text = str(exc)
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onShowFinalTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        finalModel = self._parameterNode.finalPrintableTemplateModel
        if not self.logic.isFinalPrintableTemplateModelNode(finalModel):
            slicer.util.errorDisplay(_("Select the DENTOBOT final printable template."))
            return
        finalModel.CreateDefaultDisplayNodes()
        finalModel.GetDisplayNode().SetVisibility(True)
        slicer.util.resetThreeDViews()

    def onExportFinalTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        directory = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            _("Select local folder for the verified template STL"),
            "",
        )
        if isinstance(directory, tuple):
            directory = directory[0]
        if not directory:
            return
        outputPath = Path(directory) / "DENTO_Final_Printable_Template.stl"
        overwrite = False
        if outputPath.exists():
            overwrite = slicer.util.confirmYesNoDisplay(
                _("The final template STL already exists. Replace it atomically?"),
                windowTitle=_("Replace final template STL"),
            )
            if not overwrite:
                return
        try:
            writtenPath = self.logic.exportFinalPrintableTemplateStl(
                directory,
                self._parameterNode.finalPrintableTemplateModel,
                overwrite=overwrite,
            )
            self.ui.finalVerificationStatusLabel.text = _(
                "Exported one verified printable STL: %1"
            ).replace("%1", str(writtenPath))
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #207227;"
            logging.info("Exported unified final template STL to %s", writtenPath)
        except (RuntimeError, ValueError, FileExistsError) as exc:
            self.ui.finalVerificationStatusLabel.text = str(exc)
            self.ui.finalVerificationStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def _updateLegacyTemplateFinalization(self) -> None:
        if self._updatingTemplateFinalizationUI:
            return
        if not self._parameterNode or not self.logic:
            self._clearTemplateFinalization()
            return
        if (
            self._parameterNode.templateFinalizationYawLocked
            and not self._parameterNode.templateFinalizationViewLocked
        ):
            self._parameterNode.templateFinalizationViewLocked = True

        sourceShell = self._parameterNode.researchTemplateShellModel
        sleeveModel = self._parameterNode.researchTemplateSleeveModel
        roiNode = self._parameterNode.templateShellRoi
        planeNode = self._parameterNode.templateTrimPlane
        curveNode = self._parameterNode.templateTrimCurve
        finalShell = self._parameterNode.finalizedTemplateShellModel
        mode = (
            self._parameterNode.templateFinalizationMode
            if self._parameterNode.templateFinalizationMode in {"PlaneCut", "CurveCut"}
            else "PlaneCut"
        )
        keepRegion = self._parameterNode.templateFinalizationKeepRegion
        self._bindTemplateFinalizationEditNodes(planeNode, curveNode)
        if planeNode:
            self._enforceTemplateTrimPlaneOrientation()

        sourceSummary = None
        sleeveSummary = None
        sourceError = ""
        try:
            sourceSummary = self.logic.getResearchTemplateModelSummary(
                sourceShell,
                "ResearchTemplateShell",
            )
            sleeveSummary = self.logic.getResearchTemplateModelSummary(
                sleeveModel,
                "ResearchTemplateSleeve",
            )
            if (
                sourceSummary["geometryState"] != "Current"
                or sleeveSummary["geometryState"] != "Current"
            ):
                raise ValueError(_("Regenerate stale Step 5B shell and sleeve outputs."))
            if not self.logic.isTemplateShellRoiNode(roiNode):
                raise ValueError(_("Create the locked automatic Step 5B ROI first."))
            self.logic.enforceWorkflowRoiNonInteractive(roiNode)
            if (
                sourceSummary["roi"] is not roiNode
                or roiNode.GetNodeReference(
                    self.logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
                )
                is not sourceSummary["sourceModel"]
            ):
                raise ValueError(
                    _("The current Step 5B shell and automatic ROI do not share one source.")
                )
        except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
            sourceError = str(exc)

        editNode = planeNode if mode == "PlaneCut" else curveNode
        editError = ""
        if not sourceError and editNode:
            try:
                self.logic.validateTemplateFinalizationEditNode(
                    sourceShell,
                    editNode,
                    mode,
                )
            except ValueError as exc:
                editError = str(exc)

        finalSummary = None
        finalError = ""
        if finalShell:
            try:
                finalSummary = self.logic.getFinalizedTemplateShellSummary(finalShell)
                expectedGeometryJson = (
                    self.logic.templateFinalizationEditGeometryJson(editNode, mode)
                    if editNode and not editError
                    else ""
                )
                differs = bool(
                    sourceError
                    or editError
                    or finalSummary["sourceShell"] is not sourceShell
                    or finalSummary["sourceShellUpdatedUtc"]
                    != (sourceShell.GetAttribute("DENTOBOT.UpdatedUtc") or "")
                    or finalSummary["method"] != mode
                    or finalSummary["keepRegion"] != keepRegion
                    or finalSummary["editGeometryJson"] != expectedGeometryJson
                )
                if differs:
                    self.logic.markFinalizedTemplateShellStale(
                        finalShell,
                        _("Step 5B source or Step 5C trim settings changed."),
                    )
                    finalSummary = self.logic.getFinalizedTemplateShellSummary(finalShell)
            except (RuntimeError, ValueError, json.JSONDecodeError) as exc:
                finalError = str(exc)

        self.logic.refreshWorkflowLineageColors()
        self.logic.refreshWorkflowNodeStepTags()
        lineageNode = self._lineageSourceNode(
            (finalShell, editNode, sourceShell, sleeveModel),
            self._parameterNode.targetToothSegmentId,
        )
        self._updateLineageBadge(
            self.ui.templateFinalizationLineageLabel,
            lineageNode,
            _("Step 4A → Step 4B → Step 4C → Step 5A → Step 5B → Step 5C"),
            _("Inherited lineage: waiting for a current Step 5B shell."),
        )
        for selector, acceptsNode in (
            (self.ui.templateTrimPlaneSelector, self.logic.isTemplateTrimPlaneNode),
            (self.ui.templateTrimCurveSelector, self.logic.isTemplateTrimCurveNode),
            (
                self.ui.finalizedTemplateShellModelSelector,
                self.logic.isFinalizedTemplateShellModelNode,
            ),
        ):
            self._updateNodeSelectorLineageSwatches(selector, acceptsNode)

        self._updatingTemplateFinalizationUI = True
        try:
            self.ui.templateFinalizationSourceValueLabel.text = (
                sourceShell.GetName() if sourceShell else _("--")
            )
            self.ui.templateFinalizationModeComboBox.setCurrentIndex(
                1 if mode == "CurveCut" else 0
            )
            self._setTemplateFinalizationKeepChoices(mode, keepRegion)
            self.ui.templateFinalizationViewLockedCheckBox.checked = bool(
                self._parameterNode.templateFinalizationViewLocked
                or self._parameterNode.templateFinalizationYawLocked
            )
            self.ui.templateFinalizationYawLockedCheckBox.checked = bool(
                self._parameterNode.templateFinalizationYawLocked
            )
            planeMode = mode == "PlaneCut"
            self.ui.templateTrimPlaneLabel.visible = planeMode
            self.ui.templateTrimPlaneSelector.visible = planeMode
            self.ui.createTemplateTrimPlaneButton.visible = planeMode
            self.ui.templateTrimCurveLabel.visible = not planeMode
            self.ui.templateTrimCurveSelector.visible = not planeMode
            self.ui.placeTemplateTrimCurveButton.visible = not planeMode
            sourceCurrent = not sourceError
            self.ui.continueTemplateFinalizationButton.enabled = sourceCurrent
            self.ui.createTemplateTrimPlaneButton.enabled = sourceCurrent
            self.ui.placeTemplateTrimCurveButton.enabled = sourceCurrent
            self.ui.restoreTemplateFinalizationViewButton.enabled = bool(
                self._templateFinalizationViewIsolated()
            )
            self.ui.applyTemplateFinalizationButton.enabled = bool(
                sourceCurrent and editNode and not editError
            )
            self.ui.openDynamicModelerButton.enabled = bool(
                finalSummary and finalSummary["dynamicModelerNode"]
            )
            self.ui.deleteTemplateFinalizationButton.enabled = bool(
                planeNode or curveNode or finalShell
            )
            finalCurrent = bool(
                finalSummary
                and finalSummary["geometryState"] == "Current"
                and not sourceError
                and finalSummary["sourceShell"] is sourceShell
            )
            self.ui.exportResearchTemplateButton.enabled = finalCurrent
        finally:
            self._updatingTemplateFinalizationUI = False
        self._updateTemplateFinalizationCameraFrameLabel()

        if sourceError:
            message, style = sourceError, "color: #b36b00;"
        elif finalError:
            message, style = finalError, "color: #b00020;"
        elif editError:
            message, style = editError, "color: #b36b00;"
        elif not editNode:
            message, style = (
                _("Continue to isolate the raw shell, then create the selected trim control."),
                "color: #1f5f99;",
            )
        elif finalSummary and finalSummary["geometryState"] != "Current":
            message, style = (
                _("The finalized shell is stale. Preview / Apply Trim again."),
                "color: #b36b00;",
            )
        elif finalSummary:
            message, style = (
                _("The finalized shell is current and ready for explicit Step 5C STL export."),
                "color: #207227;",
            )
        else:
            message, style = (
                _("Adjust the trim control, verify the retained region, then preview the cut."),
                "color: #1f5f99;",
            )
        self.ui.templateFinalizationStatusLabel.text = message
        self.ui.templateFinalizationStatusLabel.styleSheet = style

    def onTemplateFinalizationInputChanged(self, *args) -> None:
        del args
        if not self._updatingTemplateFinalizationUI:
            self._updateTemplateFinalization()

    def onTemplateFinalizationModeChanged(self, index: int) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        mode = self._templateFinalizationModeFromIndex(index)
        self._parameterNode.templateFinalizationMode = mode
        choices = self._templateFinalizationKeepChoices(mode)
        self._parameterNode.templateFinalizationKeepRegion = choices[0][1]
        self.logic.markFinalizedTemplateShellStale(
            self._parameterNode.finalizedTemplateShellModel,
            _("The Step 5C trim method changed."),
        )
        self._updateTemplateFinalization()

    def onTemplateFinalizationKeepRegionChanged(self, index: int) -> None:
        if (
            self._updatingTemplateFinalizationUI
            or not self._parameterNode
            or index < 0
        ):
            return
        value = self.ui.templateFinalizationKeepRegionComboBox.itemData(index)
        if value:
            self._parameterNode.templateFinalizationKeepRegion = str(value)
            self.logic.markFinalizedTemplateShellStale(
                self._parameterNode.finalizedTemplateShellModel,
                _("The Step 5C retained region changed."),
            )
        self._updateTemplateFinalization()

    def _templateFinalizationPlaneNormalWorld(self) -> tuple[float, float, float]:
        frame = self._templateFinalizationCameraFrame
        if frame:
            return frame["zAxis"]
        roiNode = self._parameterNode.templateShellRoi if self._parameterNode else None
        if roiNode and self.logic and self.logic.isTemplateShellRoiNode(roiNode):
            try:
                return self._templateFinalizationFrameFromRoi(roiNode)["zAxis"]
            except ValueError:
                pass
        return (0.0, 0.0, 1.0)

    def _enforceTemplateTrimPlaneOrientation(self) -> None:
        """Constrain the simple cut to one height along the locked ROI Z axis."""

        planeNode = self._parameterNode.templateTrimPlane if self._parameterNode else None
        if not planeNode:
            return
        roiNode = self._parameterNode.templateShellRoi
        if self.logic and self.logic.isTemplateShellRoiNode(roiNode):
            self._restoringTemplateTrimPlane = True
            try:
                self.logic.constrainTemplateTrimPlaneToRoi(planeNode, roiNode)
            finally:
                self._restoringTemplateTrimPlane = False
        else:
            normal = self._templateFinalizationPlaneNormalWorld()
            currentNormal = planeNode.GetNormalWorld()
            if any(
                abs(float(currentNormal[index]) - normal[index]) > 1e-6
                for index in range(3)
            ):
                self._restoringTemplateTrimPlane = True
                try:
                    planeNode.SetNormalWorld(normal)
                finally:
                    self._restoringTemplateTrimPlane = False
        displayNode = planeNode.GetDisplayNode()
        if displayNode:
            displayNode.SetHandlesInteractive(False)
            displayNode.SetTranslationHandleVisibility(False)
            displayNode.SetRotationHandleVisibility(False)
            displayNode.SetScaleHandleVisibility(False)
            displayNode.SetPointLabelsVisibility(False)

    def onTemplateFinalizationViewLockToggled(self, locked: bool) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        self._parameterNode.templateFinalizationViewLocked = bool(locked)
        if not locked and self._parameterNode.templateFinalizationYawLocked:
            self._parameterNode.templateFinalizationYawLocked = False
        self._enforceTemplateTrimPlaneOrientation()
        self._applyTemplateFinalizationCameraConstraints(captureYaw=True)
        self._updateTemplateFinalization()

    def onTemplateFinalizationYawLockToggled(self, locked: bool) -> None:
        if self._updatingTemplateFinalizationUI or not self._parameterNode:
            return
        self._parameterNode.templateFinalizationYawLocked = bool(locked)
        if locked:
            self._parameterNode.templateFinalizationViewLocked = True
        self._applyTemplateFinalizationCameraConstraints(captureYaw=not locked)
        self._updateTemplateFinalization()

    @staticmethod
    def _templateFinalizationVectorChanged(
        current,
        expected,
        tolerance: float = 1e-6,
    ) -> bool:
        return any(
            abs(float(current[index]) - float(expected[index])) > tolerance
            for index in range(3)
        )

    @staticmethod
    def _normalizedTemplateFinalizationAxis(values, name: str) -> tuple[float, float, float]:
        vector = np.asarray(values, dtype=float)
        length = float(np.linalg.norm(vector))
        if vector.shape != (3,) or not np.all(np.isfinite(vector)) or length <= 1e-8:
            raise ValueError(_("The Step 5B ROI has an invalid %1 axis.").replace("%1", name))
        return tuple(float(component) for component in vector / length)

    def _templateFinalizationFrameFromRoi(self, roiNode) -> dict:
        if not self.logic or not self.logic.isTemplateShellRoiNode(roiNode):
            raise ValueError(_("Create the locked automatic Step 5B ROI first."))
        self.logic.enforceWorkflowRoiNonInteractive(roiNode)
        center = [0.0, 0.0, 0.0]
        size = [0.0, 0.0, 0.0]
        roiNode.GetCenterWorld(center)
        roiNode.GetSizeWorld(size)
        if any(not math.isfinite(value) for value in (*center, *size)) or any(
            value <= 1e-6 for value in size
        ):
            raise ValueError(_("The automatic Step 5B ROI has invalid world geometry."))
        objectToWorld = roiNode.GetObjectToWorldMatrix()
        xAxis = self._normalizedTemplateFinalizationAxis(
            tuple(objectToWorld.GetElement(row, 0) for row in range(3)),
            "X",
        )
        zAxis = self._normalizedTemplateFinalizationAxis(
            tuple(objectToWorld.GetElement(row, 2) for row in range(3)),
            "Z",
        )
        yAxis = self._normalizedTemplateFinalizationAxis(
            np.cross(np.asarray(zAxis), np.asarray(xAxis)),
            "Y",
        )
        sourceYAxis = self._normalizedTemplateFinalizationAxis(
            tuple(objectToWorld.GetElement(row, 1) for row in range(3)),
            "Y",
        )
        if float(np.dot(yAxis, sourceYAxis)) < 0.0:
            yAxis = tuple(-value for value in yAxis)
            xAxis = tuple(-value for value in xAxis)
        return {
            "center": tuple(float(value) for value in center),
            "size": tuple(float(value) for value in size),
            "xAxis": xAxis,
            "yAxis": yAxis,
            "zAxis": zAxis,
            "distance": max(float(np.linalg.norm(size)) * 2.0, 20.0),
            # vtkCamera.ParallelScale is half the visible world height. Using
            # exactly half the ROI Z size aligns its top and bottom with the
            # viewport frame as requested.
            "parallelScale": max(float(size[2]) * 0.5, 0.5),
        }

    @staticmethod
    def _templateFinalizationYawFromCamera(camera, frame: dict) -> float:
        position = np.asarray(camera.GetPosition(), dtype=float)
        focalPoint = np.asarray(camera.GetFocalPoint(), dtype=float)
        outward = position - focalPoint
        xComponent = float(np.dot(outward, np.asarray(frame["xAxis"])))
        yComponent = float(np.dot(outward, np.asarray(frame["yAxis"])))
        if math.hypot(xComponent, yComponent) <= 1e-8:
            return 0.0
        return math.degrees(math.atan2(xComponent, -yComponent))

    @staticmethod
    def _templateFinalizationCameraPose(frame: dict, yawDegrees: float) -> dict:
        yawRadians = math.radians(float(yawDegrees))
        center = np.asarray(frame["center"], dtype=float)
        xAxis = np.asarray(frame["xAxis"], dtype=float)
        yAxis = np.asarray(frame["yAxis"], dtype=float)
        outward = math.sin(yawRadians) * xAxis - math.cos(yawRadians) * yAxis
        position = center + float(frame["distance"]) * outward
        return {
            "position": tuple(float(value) for value in position),
            "focalPoint": frame["center"],
            "viewUp": frame["zAxis"],
            "parallelScale": float(frame["parallelScale"]),
        }

    def _updateTemplateFinalizationCameraFrameLabel(self) -> None:
        if not hasattr(self, "ui"):
            return
        isolated = bool(self._templateFinalizationCameraFrame)
        if not isolated:
            text = _("ROI frame: +X right • +Z up • looking along +Y at yaw 0°")
        else:
            if self._parameterNode and self._parameterNode.templateFinalizationYawLocked:
                mode = _("orientation locked • zoom enabled")
            elif self._parameterNode and self._parameterNode.templateFinalizationViewLocked:
                mode = _("yaw + zoom enabled")
            else:
                mode = _("free camera")
            text = (
                _("ROI frame: +X right • +Z up • look +Y at 0° • yaw %1° • %2")
                .replace("%1", f"{self._templateFinalizationYawDegrees:.1f}")
                .replace("%2", mode)
            )
        self.ui.templateFinalizationCameraFrameLabel.text = text

    def _applyTemplateFinalizationCameraConstraints(self, captureYaw: bool) -> None:
        camera = self._templateFinalizationCamera
        frame = self._templateFinalizationCameraFrame
        if (
            not camera
            or not frame
            or self._restoringTemplateFinalizationCamera
            or not self._parameterNode
        ):
            return
        if captureYaw and not self._parameterNode.templateFinalizationYawLocked:
            self._templateFinalizationYawDegrees = self._templateFinalizationYawFromCamera(
                camera,
                frame,
            )
        if not self._parameterNode.templateFinalizationViewLocked:
            self._updateTemplateFinalizationCameraFrameLabel()
            return

        pose = self._templateFinalizationCameraPose(
            frame,
            self._templateFinalizationYawDegrees,
        )
        self._restoringTemplateFinalizationCamera = True
        try:
            if self._templateFinalizationVectorChanged(
                camera.GetFocalPoint(),
                pose["focalPoint"],
            ):
                camera.SetFocalPoint(pose["focalPoint"])
            if self._templateFinalizationVectorChanged(
                camera.GetPosition(),
                pose["position"],
            ):
                camera.SetPosition(pose["position"])
            if self._templateFinalizationVectorChanged(
                camera.GetViewUp(),
                pose["viewUp"],
            ):
                camera.SetViewUp(pose["viewUp"])
            if not camera.GetParallelProjection():
                camera.ParallelProjectionOn()
        finally:
            self._restoringTemplateFinalizationCamera = False
        self._updateTemplateFinalizationCameraFrameLabel()

    def _applyPendingTemplateFinalizationCameraConstraints(self) -> None:
        self._templateFinalizationCameraCorrectionPending = False
        self._applyTemplateFinalizationCameraConstraints(captureYaw=True)

    def _onTemplateFinalizationCameraModified(self, caller=None, event=None) -> None:
        del caller, event
        if (
            self._restoringTemplateFinalizationCamera
            or not self._templateFinalizationCameraFrame
            or self._templateFinalizationCameraCorrectionPending
        ):
            return
        self._templateFinalizationCameraCorrectionPending = True
        qt.QTimer.singleShot(
            0,
            self._applyPendingTemplateFinalizationCameraConstraints,
        )

    @staticmethod
    def _captureTemplateFinalizationCameraState(camera) -> dict | None:
        if not camera:
            return None
        return {
            "position": tuple(float(value) for value in camera.GetPosition()),
            "focalPoint": tuple(float(value) for value in camera.GetFocalPoint()),
            "viewUp": tuple(float(value) for value in camera.GetViewUp()),
            "parallelProjection": bool(camera.GetParallelProjection()),
            "parallelScale": float(camera.GetParallelScale()),
            "viewAngle": float(camera.GetViewAngle()),
            "clippingRange": tuple(float(value) for value in camera.GetClippingRange()),
        }

    def _prepareTemplateFinalizationView(self, sourceShell, *, resetYaw: bool = False) -> None:
        if self._trajectoryVerificationEnabled:
            self._restoreTrajectoryVerificationViewState(updateUi=True)
        roiNode = self._parameterNode.templateShellRoi if self._parameterNode else None
        frame = self._templateFinalizationFrameFromRoi(roiNode)
        sourceSummary = self.logic.getResearchTemplateModelSummary(
            sourceShell,
            "ResearchTemplateShell",
        )
        if (
            sourceSummary["roi"] is not roiNode
            or roiNode.GetNodeReference(
                self.logic.TEMPLATE_GUIDE_SOURCE_MODEL_REFERENCE_ROLE
            )
            is not sourceSummary["sourceModel"]
        ):
            raise ValueError(_("The Step 5B shell and automatic ROI do not share one source."))

        layoutManager = slicer.app.layoutManager()
        if not layoutManager:
            raise RuntimeError(_("Slicer's layout manager is unavailable."))
        firstIsolation = self._templateFinalizationPriorLayoutId is None
        if firstIsolation:
            self._templateFinalizationPriorLayoutId = int(layoutManager.layout)
            if layoutManager.threeDViewCount >= 1:
                priorView = layoutManager.threeDWidget(0).threeDView()
                self._templateFinalizationPriorCameraState = (
                    self._captureTemplateFinalizationCameraState(
                        priorView.cameraNode().GetCamera()
                    )
                )
                priorViewNode = priorView.mrmlViewNode()
                if priorViewNode:
                    self._templateFinalizationPriorViewNodeState = {
                        "axisLabelsVisible": bool(
                            priorViewNode.GetAxisLabelsVisible()
                        ),
                        "orientationMarkerType": int(
                            priorViewNode.GetOrientationMarkerType()
                        ),
                        "orientationMarkerSize": int(
                            priorViewNode.GetOrientationMarkerSize()
                        ),
                    }
            crosshairNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCrosshairNode")
            if crosshairNode:
                self._templateFinalizationPriorCrosshairMode = int(
                    crosshairNode.GetCrosshairMode()
                )
                crosshairNode.SetCrosshairMode(0)
        if not self._templateFinalizationPriorVisibilityByNodeId:
            for nodeIndex in range(slicer.mrmlScene.GetNumberOfNodes()):
                node = slicer.mrmlScene.GetNthNode(nodeIndex)
                if not node or not node.IsA("vtkMRMLDisplayableNode"):
                    continue
                displayNode = node.GetDisplayNode()
                if displayNode and node.GetID():
                    self._templateFinalizationPriorVisibilityByNodeId[node.GetID()] = bool(
                        displayNode.GetVisibility()
                    )
        for nodeId in self._templateFinalizationPriorVisibilityByNodeId:
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            displayNode = node.GetDisplayNode() if node else None
            if displayNode:
                displayNode.SetVisibility(False)
        sourceShell.GetDisplayNode().SetVisibility(True)
        editNode = (
            self._parameterNode.templateTrimPlane
            if self._parameterNode.templateFinalizationMode == "PlaneCut"
            else self._parameterNode.templateTrimCurve
        )
        if editNode and editNode.GetDisplayNode():
            editNode.GetDisplayNode().SetVisibility(True)

        if firstIsolation:
            layoutManager.setLayout(
                slicer.vtkMRMLLayoutNode.SlicerLayoutOneUp3DView
            )
        if not layoutManager or layoutManager.threeDViewCount < 1:
            raise RuntimeError(_("No Slicer 3D view is available."))
        threeDView = layoutManager.threeDWidget(0).threeDView()
        viewNode = threeDView.mrmlViewNode()
        if viewNode:
            viewNode.SetAxisLabelsVisible(False)
            viewNode.SetOrientationMarkerType(
                slicer.vtkMRMLAbstractViewNode.OrientationMarkerTypeAxes
            )
            viewNode.SetOrientationMarkerSize(
                slicer.vtkMRMLAbstractViewNode.OrientationMarkerSizeMedium
            )
        camera = threeDView.cameraNode().GetCamera()
        if self._templateFinalizationCamera is not camera:
            if self._templateFinalizationCamera:
                self.removeObserver(
                    self._templateFinalizationCamera,
                    vtk.vtkCommand.ModifiedEvent,
                    self._onTemplateFinalizationCameraModified,
                )
            self._templateFinalizationCamera = camera
            self.addObserver(
                camera,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateFinalizationCameraModified,
            )
        self._templateFinalizationCameraFrame = frame
        if resetYaw:
            self._templateFinalizationYawDegrees = 0.0
        pose = self._templateFinalizationCameraPose(
            frame,
            self._templateFinalizationYawDegrees,
        )
        self._restoringTemplateFinalizationCamera = True
        try:
            camera.SetFocalPoint(pose["focalPoint"])
            camera.SetPosition(pose["position"])
            camera.SetViewUp(pose["viewUp"])
            camera.ParallelProjectionOn()
            if firstIsolation or resetYaw:
                camera.SetParallelScale(pose["parallelScale"])
        finally:
            self._restoringTemplateFinalizationCamera = False
        renderer = threeDView.renderWindow().GetRenderers().GetFirstRenderer()
        if renderer:
            renderer.ResetCameraClippingRange()
        self._enforceTemplateTrimPlaneOrientation()
        self._applyTemplateFinalizationCameraConstraints(captureYaw=False)
        self._updateTemplateFinalizationCameraFrameLabel()
        threeDView.forceRender()

    def onContinueTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            sourceShell = self.logic.validateTemplateFinalizationSourceShell(
                self._parameterNode.researchTemplateShellModel
            )
            if self._parameterNode.templateFinalizationMode == "PlaneCut":
                planeNode = self._parameterNode.templateTrimPlane
                if planeNode:
                    self._enforceTemplateTrimPlaneOrientation()
                    self.logic.validateTemplateFinalizationEditNode(
                        sourceShell,
                        planeNode,
                        "PlaneCut",
                        requireComplete=False,
                    )
            else:
                curveNode = self._parameterNode.templateTrimCurve
                if curveNode:
                    self.logic.validateTemplateFinalizationEditNode(
                        sourceShell,
                        curveNode,
                        "CurveCut",
                        requireComplete=False,
                    )
            self._prepareTemplateFinalizationView(sourceShell, resetYaw=True)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onCreateTemplateTrimPlane(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            planeNode = self.logic.createOrResetTemplateTrimPlane(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.templateTrimPlane,
            )
            self._parameterNode.templateTrimPlane = planeNode
            self._enforceTemplateTrimPlaneOrientation()
            self._prepareTemplateFinalizationView(
                self._parameterNode.researchTemplateShellModel
            )
            self.logic.startHorizontalPlanePlacement(planeNode)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onPlaceTemplateTrimCurve(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            curveNode = self._parameterNode.templateTrimCurve
            if not curveNode:
                curveNode = self.logic.createTemplateTrimCurve(
                    self._parameterNode.researchTemplateShellModel
                )
                self._parameterNode.templateTrimCurve = curveNode
            else:
                self.logic.validateTemplateFinalizationEditNode(
                    self._parameterNode.researchTemplateShellModel,
                    curveNode,
                    "CurveCut",
                    requireComplete=False,
                )
            self._prepareTemplateFinalizationView(
                self._parameterNode.researchTemplateShellModel
            )
            self.logic.startClosedCurvePlacement(curveNode)
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onApplyTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            self.logic.stopTrajectoryPlacement()
            if self._parameterNode.templateFinalizationMode == "PlaneCut":
                self._enforceTemplateTrimPlaneOrientation()
            finalShell, details = self.logic.createOrUpdateFinalizedTemplateShell(
                self._parameterNode.researchTemplateShellModel,
                self._parameterNode.templateTrimPlane,
                self._parameterNode.templateTrimCurve,
                self._parameterNode.templateFinalizationMode,
                self._parameterNode.templateFinalizationKeepRegion,
                self._parameterNode.finalizedTemplateShellModel,
            )
            self._parameterNode.finalizedTemplateShellModel = finalShell
            sourceDisplay = self._parameterNode.researchTemplateShellModel.GetDisplayNode()
            if sourceDisplay:
                sourceDisplay.SetVisibility(False)
            if finalShell.GetDisplayNode():
                finalShell.GetDisplayNode().SetVisibility(True)
            logging.info(
                "Generated DENTOBOT Step 5C finalized shell using %s/%s (%d triangles)",
                details["method"],
                details["keepRegion"],
                details["topology"]["triangleCount"],
            )
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            self.ui.templateFinalizationStatusLabel.text = str(exc)
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #b00020;"
            slicer.util.errorDisplay(str(exc))

    def onRestoreTemplateFinalizationView(self) -> None:
        self._restoreTemplateFinalizationViewState(updateUi=True)

    def _templateFinalizationViewIsolated(self) -> bool:
        return bool(
            self._templateFinalizationPriorLayoutId is not None
            or self._templateFinalizationPriorVisibilityByNodeId
            or self._templateFinalizationCameraFrame
        )

    def _restoreTemplateFinalizationViewState(self, *, updateUi: bool) -> None:
        """Restore all presentation state captured on entry to Step 5C isolation."""

        if self._templateFinalizationCamera:
            self.removeObserver(
                self._templateFinalizationCamera,
                vtk.vtkCommand.ModifiedEvent,
                self._onTemplateFinalizationCameraModified,
            )
        self._templateFinalizationCamera = None
        self._templateFinalizationCameraFrame = None
        self._templateFinalizationCameraCorrectionPending = False

        layoutManager = slicer.app.layoutManager() if slicer.app else None
        if layoutManager and self._templateFinalizationPriorLayoutId is not None:
            layoutManager.setLayout(self._templateFinalizationPriorLayoutId)

        if (
            layoutManager
            and layoutManager.threeDViewCount >= 1
            and self._templateFinalizationPriorCameraState
        ):
            threeDView = layoutManager.threeDWidget(0).threeDView()
            viewNode = threeDView.mrmlViewNode()
            if viewNode and self._templateFinalizationPriorViewNodeState:
                viewState = self._templateFinalizationPriorViewNodeState
                viewNode.SetAxisLabelsVisible(viewState["axisLabelsVisible"])
                viewNode.SetOrientationMarkerType(
                    viewState["orientationMarkerType"]
                )
                viewNode.SetOrientationMarkerSize(
                    viewState["orientationMarkerSize"]
                )
            camera = threeDView.cameraNode().GetCamera()
            state = self._templateFinalizationPriorCameraState
            self._restoringTemplateFinalizationCamera = True
            try:
                camera.SetFocalPoint(state["focalPoint"])
                camera.SetPosition(state["position"])
                camera.SetViewUp(state["viewUp"])
                camera.SetParallelProjection(state["parallelProjection"])
                camera.SetParallelScale(state["parallelScale"])
                camera.SetViewAngle(state["viewAngle"])
                camera.SetClippingRange(state["clippingRange"])
            finally:
                self._restoringTemplateFinalizationCamera = False
            threeDView.forceRender()

        crosshairNode = slicer.mrmlScene.GetFirstNodeByClass("vtkMRMLCrosshairNode")
        if crosshairNode and self._templateFinalizationPriorCrosshairMode is not None:
            crosshairNode.SetCrosshairMode(self._templateFinalizationPriorCrosshairMode)

        for nodeId, visibility in self._templateFinalizationPriorVisibilityByNodeId.items():
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            displayNode = node.GetDisplayNode() if node else None
            if displayNode:
                displayNode.SetVisibility(visibility)
        self._templateFinalizationPriorVisibilityByNodeId.clear()
        self._templateFinalizationPriorLayoutId = None
        self._templateFinalizationPriorCameraState = None
        self._templateFinalizationPriorViewNodeState = None
        self._templateFinalizationPriorCrosshairMode = None
        self._updateTemplateFinalizationCameraFrameLabel()
        if updateUi and self._parameterNode:
            self._updateTemplateFinalization()

    def onOpenDynamicModeler(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        try:
            summary = self.logic.getFinalizedTemplateShellSummary(
                self._parameterNode.finalizedTemplateShellModel
            )
            dynamicNode = summary["dynamicModelerNode"]
            if not dynamicNode:
                raise ValueError(_("Apply a Step 5C trim before opening Dynamic Modeler."))
            slicer.util.selectModule("DynamicModeler")
            moduleWidget = slicer.modules.dynamicmodeler.widgetRepresentation()
            treeView = slicer.util.findChild(moduleWidget, "SubjectHierarchyTreeView")
            if treeView:
                treeView.setCurrentNode(dynamicNode)
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onDeleteTemplateFinalization(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        if not slicer.util.confirmYesNoDisplay(
            _(
                "Delete the Step 5C plane, curve, finalized shell, and owned "
                "Dynamic Modeler auxiliaries? The raw Step 5B shell and sleeve will be kept."
            ),
            windowTitle=_("Delete Step 5C fit and trim"),
        ):
            return
        try:
            removals = self.logic.deleteTemplateFinalization(
                self._parameterNode.templateTrimPlane,
                self._parameterNode.templateTrimCurve,
                self._parameterNode.finalizedTemplateShellModel,
            )
            self._parameterNode.templateTrimPlane = None
            self._parameterNode.templateTrimCurve = None
            self._parameterNode.finalizedTemplateShellModel = None
            logging.info("Deleted %d DENTOBOT Step 5C nodes", len(removals))
            self._updateTemplateFinalization()
        except (RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))

    def onExportResearchTemplate(self) -> None:
        if not self._parameterNode or not self.logic:
            return
        directory = qt.QFileDialog.getExistingDirectory(
            slicer.util.mainWindow(),
            _("Select local folder for research STL files"),
            "",
        )
        if isinstance(directory, tuple):
            directory = directory[0]
        if not directory:
            return
        outputPaths = (
            Path(directory) / "DENTO_Research_Template_Shell.stl",
            Path(directory) / "DENTO_Research_Template_Sleeve.stl",
        )
        overwrite = False
        if any(path.exists() for path in outputPaths):
            overwrite = slicer.util.confirmYesNoDisplay(
                _("One or both STL files already exist. Replace them atomically?"),
                windowTitle=_("Replace research STL files"),
            )
            if not overwrite:
                return
        try:
            paths = self.logic.exportResearchTemplateStls(
                directory,
                self._parameterNode.finalizedTemplateShellModel,
                self._parameterNode.researchTemplateSleeveModel,
                overwrite=overwrite,
            )
            self.ui.templateFinalizationStatusLabel.text = (
                _("Exported research STL files: %1 and %2")
                .replace("%1", str(paths["shell"]))
                .replace("%2", str(paths["sleeve"]))
            )
            self.ui.templateFinalizationStatusLabel.styleSheet = "color: #207227;"
        except (OSError, RuntimeError, ValueError) as exc:
            slicer.util.errorDisplay(str(exc))
