"""Extracted workflow panel construction methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class WorkflowPanelsWidgetMixin:
    def _setupUnifiedTemplateBuildPanel(self) -> None:
        """Present Step 5B as one ordered, dependency-aware build workflow."""

        if self._unifiedTemplateInputsGroup is not None:
            return

        stageLayout = self.ui.templateGuideVerticalLayout
        self.ui.templateGuideCollapsibleButton.text = _(
            "Step 5B — Build Unified Template"
        )
        self.ui.templateGuideDescriptionLabel.text = _(
            "Build one unified research template from the approved Step 4A "
            "trajectory, Step 4B support draft, confirmed Step 4C rails/docks, "
            "and Step 5A visible support surface. Set every dimension before "
            "using the single build action at the bottom."
        )

        # The Designer order placed the result and actions before several
        # generation parameters. Move the existing widgets—without duplicating
        # their parameter-node bindings—into an explicit operator sequence.
        for widget in (
            self.ui.templateGuideLineageLabel,
            self.ui.patientContactShellGroupBox,
            self.ui.templateDockingFusionGroupBox,
        ):
            stageLayout.removeWidget(widget)

        readinessGroup = qt.QGroupBox(
            _("1 · Approved inputs and lineage"),
            self.ui.templateGuideCollapsibleButton,
        )
        readinessGroup.objectName = "unifiedTemplateReadinessGroupBox"
        readinessLayout = qt.QVBoxLayout(readinessGroup)
        readinessLayout.setContentsMargins(8, 8, 8, 8)
        readinessLayout.setSpacing(5)
        readinessHelp = qt.QLabel(
            _(
                "The complete build validates these references first and stops "
                "before voxel processing when a source is missing, stale, "
                "unconfirmed, or unlocked."
            ),
            readinessGroup,
        )
        readinessHelp.objectName = "unifiedTemplateReadinessHelpLabel"
        readinessHelp.wordWrap = True
        readinessHelp.styleSheet = "color: #555555;"
        readinessLayout.addWidget(readinessHelp)
        readinessLayout.addWidget(self.ui.templateGuideLineageLabel)

        sourceTrajectories = ctk.ctkCollapsibleButton(readinessGroup)
        sourceTrajectories.objectName = "unifiedTemplateSourceTrajectoriesGroupBox"
        sourceTrajectories.text = _("Approved source trajectories — read only")
        sourceTrajectories.collapsed = True
        sourceTrajectoriesLayout = qt.QVBoxLayout(sourceTrajectories)
        sourceTrajectoriesLayout.setContentsMargins(8, 8, 8, 8)
        self.ui.templateDockingFusionVerticalLayout.removeWidget(
            self.ui.templateGuideTrajectoriesListWidget
        )
        self.ui.templateGuideTrajectoriesListWidget.setMinimumHeight(80)
        sourceTrajectoriesLayout.addWidget(
            self.ui.templateGuideTrajectoriesListWidget
        )
        readinessLayout.addWidget(sourceTrajectories)

        inputsGroup = ctk.ctkCollapsibleButton(
            self.ui.templateGuideCollapsibleButton
        )
        inputsGroup.objectName = "unifiedTemplateInputsGroupBox"
        inputsGroup.text = _("2 · Unified template dimensions")
        inputsGroup.collapsed = False
        inputsLayout = qt.QVBoxLayout(inputsGroup)
        inputsLayout.setContentsMargins(8, 8, 8, 8)
        inputsLayout.setSpacing(6)
        inputsHelp = qt.QLabel(
            _(
                "Changing any value marks the affected cached stage stale. "
                "Build / Update regenerates only the stages that require it."
            ),
            inputsGroup,
        )
        inputsHelp.objectName = "unifiedTemplateInputsHelpLabel"
        inputsHelp.wordWrap = True
        inputsHelp.styleSheet = "color: #555555;"
        inputsLayout.addWidget(inputsHelp)

        shellDimensions = qt.QGroupBox(_("Patient-contact shell"), inputsGroup)
        shellDimensions.objectName = "unifiedTemplateShellDimensionsGroupBox"
        shellForm = qt.QFormLayout(shellDimensions)
        guideDimensions = qt.QGroupBox(_("Trajectory guide"), inputsGroup)
        guideDimensions.objectName = "unifiedTemplateGuideDimensionsGroupBox"
        guideForm = qt.QFormLayout(guideDimensions)
        fusionDimensions = qt.QGroupBox(_("Guide and dock fusion"), inputsGroup)
        fusionDimensions.objectName = "unifiedTemplateFusionDimensionsGroupBox"
        fusionForm = qt.QFormLayout(fusionDimensions)

        def moveFormRow(sourceLayout, label, field, destinationLayout) -> None:
            sourceLayout.removeWidget(label)
            sourceLayout.removeWidget(field)
            destinationLayout.addRow(label, field)

        for label, field in (
            (self.ui.templateShellClearanceLabel, self.ui.templateShellClearanceSpinBox),
            (self.ui.templateShellThicknessLabel, self.ui.templateShellThicknessSpinBox),
            (self.ui.templateSamplingSpacingLabel, self.ui.templateSamplingSpacingSpinBox),
        ):
            moveFormRow(self.ui.templateGuideFormLayout, label, field, shellForm)
        for label, field in (
            (
                self.ui.templateSleeveOuterDiameterLabel,
                self.ui.templateSleeveOuterDiameterSpinBox,
            ),
            (
                self.ui.templateSleeveInnerDiameterLabel,
                self.ui.templateSleeveInnerDiameterSpinBox,
            ),
            (self.ui.templateSleeveHeightLabel, self.ui.templateSleeveHeightSpinBox),
        ):
            moveFormRow(self.ui.templateGuideFormLayout, label, field, guideForm)
        for label, field in (
            (
                self.ui.templateDockingClearanceLabel,
                self.ui.templateDockingClearanceSpinBox,
            ),
            (
                self.ui.templateReinforcementRadialLabel,
                self.ui.templateReinforcementRadialSpinBox,
            ),
            (
                self.ui.templateReinforcementDepthLabel,
                self.ui.templateReinforcementDepthSpinBox,
            ),
        ):
            moveFormRow(
                self.ui.templateDockingFusionFormLayout,
                label,
                field,
                fusionForm,
            )
        inputsLayout.addWidget(shellDimensions)
        inputsLayout.addWidget(guideDimensions)
        inputsLayout.addWidget(fusionDimensions)

        advancedGroup = self.ui.patientContactShellGroupBox
        advancedGroup.text = _(
            "Advanced · Fit processing and cached intermediate shell"
        )
        advancedGroup.collapsed = True
        advancedHelp = qt.QLabel(
            _(
                "Optional diagnostic controls for undercut/blockout analysis "
                "and the cached patient shell. Routine generation does not "
                "require these staged buttons; the complete build below runs "
                "or reuses them automatically."
            ),
            advancedGroup,
        )
        advancedHelp.objectName = "unifiedTemplateAdvancedHelpLabel"
        advancedHelp.wordWrap = True
        advancedHelp.styleSheet = "color: #555555;"
        self.ui.patientContactShellVerticalLayout.insertWidget(0, advancedHelp)

        resultGroup = self.ui.templateDockingFusionGroupBox
        resultGroup.text = _("3 · Unified template result")
        resultGroup.collapsed = False
        resultLayout = self.ui.templateDockingFusionVerticalLayout
        self.ui.templateDockingFusionDescriptionLabel.text = _(
            "This is the generated Step 5B geometry. Current means its inputs "
            "match; Step 5C verification is still required before export."
        )
        self.ui.templateDockingFusionFormLayout.removeWidget(
            self.ui.finalPrintableTemplateModelLabel
        )
        self.ui.templateDockingFusionFormLayout.removeWidget(
            self.ui.finalPrintableTemplateModelSelector
        )
        self.ui.templateDockingFusionButtonLayout.removeWidget(
            self.ui.generateFinalPrintableTemplateButton
        )
        self.ui.templateDockingFusionButtonLayout.removeWidget(
            self.ui.deleteFinalPrintableTemplateButton
        )
        inspectionButtons = (
            self.ui.inspectTemplateFitButton,
            self.ui.inspectShellAndGuidesButton,
            self.ui.inspectUnifiedTemplateButton,
        )
        for button in inspectionButtons:
            self.ui.templateInspectionButtonLayout.removeWidget(button)
        resultLayout.removeWidget(self.ui.templateDockingFusionStatusLabel)
        resultForm = qt.QFormLayout()
        resultForm.addRow(
            self.ui.finalPrintableTemplateModelLabel,
            self.ui.finalPrintableTemplateModelSelector,
        )
        resultLayout.addLayout(resultForm)
        resultLayout.addWidget(self.ui.templateDockingFusionStatusLabel)

        actionGroup = qt.QGroupBox(
            _("4 · Build and inspect"),
            self.ui.templateGuideCollapsibleButton,
        )
        actionGroup.objectName = "unifiedTemplateActionGroupBox"
        actionLayout = qt.QVBoxLayout(actionGroup)
        actionLayout.setContentsMargins(8, 8, 8, 8)
        actionLayout.setSpacing(6)
        self.ui.generateFinalPrintableTemplateButton.text = _(
            "Build / Update Unified Template"
        )
        self.ui.generateFinalPrintableTemplateButton.toolTip = _(
            "Validate the approved upstream package, then generate only a "
            "missing or stale blockout, cached patient shell, or unified "
            "guide/dock fusion. Current cached geometry is reused."
        )
        self.ui.generateFinalPrintableTemplateButton.setMinimumHeight(34)
        self.ui.generateFinalPrintableTemplateButton.styleSheet = (
            "font-weight: 600;"
        )
        actionLayout.addWidget(self.ui.generateFinalPrintableTemplateButton)
        inspectionLabel = qt.QLabel(_("Display-only inspection:"), actionGroup)
        inspectionLabel.objectName = "unifiedTemplateInspectionLabel"
        inspectionLabel.styleSheet = "font-weight: 600;"
        actionLayout.addWidget(inspectionLabel)
        inspectionLayout = qt.QHBoxLayout()
        for button in inspectionButtons:
            inspectionLayout.addWidget(button)
        actionLayout.addLayout(inspectionLayout)
        deleteLayout = qt.QHBoxLayout()
        deleteLayout.addStretch(1)
        self.ui.deleteFinalPrintableTemplateButton.text = _(
            "Delete Unified Template…"
        )
        deleteLayout.addWidget(self.ui.deleteFinalPrintableTemplateButton)
        actionLayout.addLayout(deleteLayout)

        # Visible order is prerequisites → all parameters → optional
        # intermediates → result → actions. Hidden legacy adapters remain for
        # saved-scene compatibility only.
        stageLayout.insertWidget(1, readinessGroup)
        stageLayout.insertWidget(2, inputsGroup)
        stageLayout.insertWidget(3, advancedGroup)
        stageLayout.insertWidget(4, resultGroup)
        stageLayout.insertWidget(5, actionGroup)
        self._unifiedTemplateReadinessGroup = readinessGroup
        self._unifiedTemplateInputsGroup = inputsGroup
        self._unifiedTemplateActionGroup = actionGroup

    def _setupTrajectoryPlanningModes(self) -> None:
        """Place manual/assisted initialization behind one Step 4A choice."""

        comboBox = self.ui.trajectoryPlacementModeComboBox
        comboBox.clear()
        comboBox.addItem(_("Manual Entry → Target placement"), "Manual")
        comboBox.addItem(_("Assisted root-target initializer"), "Assisted")
        comboBox.connect(
            "currentIndexChanged(int)", self.onTrajectoryPlacementModeChanged
        )

        # Assisted initialization is not a parallel workflow step. Nest its
        # existing controls inside Step 4A before the common planning/MPR view.
        if self._workflowContentLayout:
            self._workflowContentLayout.removeWidget(
                self.ui.assistedTrajectoryCollapsibleButton
            )
        self.ui.planningVerticalLayout.insertWidget(
            3,
            self.ui.assistedTrajectoryCollapsibleButton,
        )
        self.ui.assistedTrajectoryCollapsibleButton.text = _(
            "Assisted placement controls"
        )
        self.ui.planningViewControlsGroupBox.title = _(
            "Planning view — shared by manual and assisted placement"
        )
        self.ui.trajectoryVerificationGroupBox.text = _(
            "Trajectory Verification — shared longitudinal oblique MPR"
        )

    def _setupTemplateSupportArchSelector(self) -> None:
        """Build the Step 4B editor and the Step 5A read-only package card."""

        formLayout = self.ui.templateModelingFormLayout
        formLayout.removeWidget(self.ui.templateSupportTeethListWidget)
        self.ui.templateSupportTeethListWidget.visible = False
        # The QListWidget remains a hidden scene-state adapter for the existing
        # itemChanged handler.  It must never be made visible after removal
        # from the form layout, otherwise Qt treats it as an unmanaged child
        # and it floats over the visual arch controls.
        formLayout.removeWidget(self.ui.templateSupportTeethTitleLabel)
        self.ui.templateSupportTeethTitleLabel.visible = False
        archWidget = qt.QGroupBox(
            _("Select and lock the Step 4B support package"),
            self.ui.templateModelingCollapsibleButton,
        )
        archWidget.objectName = "templateSupportArchSelectorWidget"
        archWidget.setSizePolicy(
            qt.QSizePolicy.Expanding,
            qt.QSizePolicy.Minimum,
        )
        archWidget.setMinimumHeight(178)
        archLayout = qt.QVBoxLayout(archWidget)
        archLayout.setContentsMargins(8, 8, 8, 8)
        archLayout.setSpacing(6)
        orientationLabel = qt.QLabel(
            _(
                "Patient right and left halves are shown back→centre. "
                "Click teeth to add/remove support, then create the draft to "
                "lock the package."
            ),
            archWidget,
        )
        orientationLabel.wordWrap = True
        orientationLabel.styleSheet = "color: #555555;"
        archLayout.addWidget(orientationLabel)
        gridWidget = qt.QWidget(archWidget)
        gridWidget.objectName = "templateSupportArchGridWidget"
        gridWidget.setSizePolicy(
            qt.QSizePolicy.Expanding,
            qt.QSizePolicy.Fixed,
        )
        gridWidget.setMinimumHeight(112)
        gridLayout = qt.QGridLayout(gridWidget)
        gridLayout.setContentsMargins(0, 0, 0, 0)
        gridLayout.setHorizontalSpacing(3)
        gridLayout.setVerticalSpacing(3)
        archLayout.addWidget(gridWidget)
        statusLabel = qt.QLabel(
            _("Select a Step 4A target tooth to show its jaw."),
            archWidget,
        )
        statusLabel.wordWrap = True
        statusLabel.styleSheet = "color: #1f5f99;"
        archLayout.addWidget(statusLabel)
        reviseButton = qt.QPushButton(
            _("Revise locked support package…"),
            archWidget,
        )
        reviseButton.objectName = "reviseTemplateSupportPackageButton"
        reviseButton.enabled = False
        reviseButton.toolTip = _(
            "Unlock Step 4B support-tooth selection and mark every dependent "
            "Step 4C/5A/5B/5C result stale. Rebuild the draft to lock it again."
        )
        archLayout.addWidget(reviseButton)
        formLayout.setWidget(1, qt.QFormLayout.SpanningRole, archWidget)
        self._templateSupportArchWidget = archWidget
        self._templateSupportArchGridLayout = gridLayout
        self._templateSupportArchStatusLabel = statusLabel
        self._reviseTemplateSupportPackageButton = reviseButton

        packageWidget = qt.QGroupBox(
            _("Locked Step 4B support package"),
            self.ui.templateModelingCollapsibleButton,
        )
        packageWidget.objectName = "templateSupportPackageWidget"
        packageWidget.setSizePolicy(
            qt.QSizePolicy.Expanding,
            qt.QSizePolicy.Minimum,
        )
        packageLayout = qt.QVBoxLayout(packageWidget)
        packageLayout.setContentsMargins(8, 8, 8, 8)
        packageLayout.setSpacing(6)
        packageSummaryLabel = qt.QLabel(
            _("No locked Step 4B support package is available."),
            packageWidget,
        )
        packageSummaryLabel.objectName = "templateSupportPackageSummaryLabel"
        packageSummaryLabel.wordWrap = True
        packageSummaryLabel.styleSheet = (
            "QLabel { color: #b36b00; background: #fff5df; "
            "border-left: 6px solid #b36b00; padding: 6px; }"
        )
        packageLayout.addWidget(packageSummaryLabel)
        packageDetailsLabel = qt.QLabel("", packageWidget)
        packageDetailsLabel.objectName = "templateSupportPackageDetailsLabel"
        packageDetailsLabel.wordWrap = True
        packageDetailsLabel.textInteractionFlags = qt.Qt.TextSelectableByMouse
        packageLayout.addWidget(packageDetailsLabel)
        returnButton = qt.QPushButton(
            _("Return to Step 4B to change support teeth"),
            packageWidget,
        )
        returnButton.objectName = "returnToStep4BSupportButton"
        returnButton.toolTip = _(
            "Step 5A never edits support-tooth membership. Return to Step 4B "
            "to explicitly unlock, revise, and rebuild the support package."
        )
        packageLayout.addWidget(returnButton)
        self.ui.templateModelingVerticalLayout.insertWidget(2, packageWidget)
        packageWidget.visible = False
        self._templateSupportPackageWidget = packageWidget
        self._templateSupportPackageSummaryLabel = packageSummaryLabel
        self._templateSupportPackageDetailsLabel = packageDetailsLabel
        self._returnToStep4BSupportButton = returnButton

    @staticmethod
    def _templateSupportArchRows(targetFdi: str) -> tuple[list[str], list[str]]:
        quadrant = targetFdi[:1]
        if quadrant in {"1", "2"}:
            return (
                [f"1{number}" for number in range(8, 0, -1)],
                [f"2{number}" for number in range(8, 0, -1)],
            )
        if quadrant in {"3", "4"}:
            return (
                [f"4{number}" for number in range(8, 0, -1)],
                [f"3{number}" for number in range(8, 0, -1)],
            )
        return ([], [])

    @staticmethod
    def _templateSupportToothIcon(color: qt.QColor) -> qt.QIcon:
        pixmap = qt.QPixmap(26, 30)
        pixmap.fill(qt.Qt.transparent)
        painter = qt.QPainter(pixmap)
        painter.setRenderHint(qt.QPainter.Antialiasing, True)
        pen = qt.QPen(color)
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(qt.QBrush(color.lighter(165)))
        painter.drawRoundedRect(qt.QRectF(4.0, 2.0, 18.0, 16.0), 5.0, 5.0)
        painter.drawLine(9, 17, 8, 28)
        painter.drawLine(17, 17, 18, 28)
        painter.end()
        return qt.QIcon(pixmap)

    def _clearTemplateSupportArchButtons(self) -> None:
        layout = self._templateSupportArchGridLayout
        if not layout:
            return
        while self._qtLayoutCount(layout):
            item = layout.takeAt(0)
            widget = item.widget() if item and hasattr(item, "widget") else None
            if widget:
                widget.deleteLater()
        self._templateSupportButtonsBySegmentId.clear()

    def _rebuildTemplateSupportArchSelector(
        self,
        targetRecord: dict | None,
        availableRecords: list[dict],
        selectedSupportIds: list[str],
    ) -> None:
        self._clearTemplateSupportArchButtons()
        if not targetRecord:
            self._templateSupportArchStatusLabel.text = _(
                "Select a Step 4A target tooth to show its jaw."
            )
            self._templateSupportArchStatusLabel.styleSheet = "color: #b36b00;"
            return
        targetFdi = str(targetRecord.get("fdiNumber") or "")
        rows = self._templateSupportArchRows(targetFdi)
        recordsByFdi = {
            str(record.get("fdiNumber") or ""): record
            for record in availableRecords
            if record.get("fdiNumber")
        }
        recordsByFdi[targetFdi] = targetRecord
        selectedIds = set(selectedSupportIds)
        targetColor = qt.QColor("#F0A020")
        supportColor = qt.QColor("#258B8B")
        availableColor = qt.QColor("#6D7882")
        missingColor = qt.QColor("#B8BEC4")
        for rowIndex, fdiRow in enumerate(rows):
            for columnIndex, fdiNumber in enumerate(fdiRow):
                record = recordsByFdi.get(fdiNumber)
                isTarget = fdiNumber == targetFdi
                isAvailable = bool(record)
                segmentId = record["segmentId"] if record else ""
                selected = bool(segmentId and segmentId in selectedIds)
                button = qt.QToolButton(self._templateSupportArchWidget)
                button.objectName = f"templateSupportToothFdi{fdiNumber}Button"
                button.text = fdiNumber
                button.toolButtonStyle = qt.Qt.ToolButtonTextUnderIcon
                button.iconSize = qt.QSize(24, 28)
                button.setMinimumSize(38, 52)
                button.checkable = bool(isAvailable)
                button.checked = bool(selected or isTarget)
                button.enabled = bool(isAvailable and not isTarget)
                iconColor = (
                    targetColor
                    if isTarget
                    else supportColor
                    if selected
                    else availableColor
                    if isAvailable
                    else missingColor
                )
                button.icon = self._templateSupportToothIcon(iconColor)
                if isTarget:
                    button.toolTip = _(
                        "FDI %1 — TARGET TOOTH. Always included and locked."
                    ).replace("%1", fdiNumber)
                    button.styleSheet = (
                        "QToolButton { background: #FFE6B5; border: 2px solid "
                        "#F0A020; border-radius: 6px; font-weight: 700; }"
                    )
                elif isAvailable:
                    button.toolTip = _(
                        "FDI %1 — click to toggle this same-jaw support tooth."
                    ).replace("%1", fdiNumber)
                    button.styleSheet = (
                        "QToolButton { border: 1px solid #8A949C; border-radius: 6px; } "
                        "QToolButton:checked { background: #CDEFEF; border: 2px solid "
                        "#258B8B; font-weight: 700; }"
                    )
                    button.connect(
                        "toggled(bool)",
                        lambda checked, supportId=segmentId: (
                            self.onTemplateSupportArchButtonToggled(
                                supportId,
                                checked,
                            )
                        ),
                    )
                    self._templateSupportButtonsBySegmentId[segmentId] = button
                else:
                    button.toolTip = _(
                        "FDI %1 is not present as a whole-tooth segment."
                    ).replace("%1", fdiNumber)
                    button.styleSheet = (
                        "QToolButton { color: #999999; border: 1px dashed #BBBBBB; "
                        "border-radius: 6px; }"
                    )
                self._templateSupportArchGridLayout.addWidget(
                    button,
                    rowIndex,
                    columnIndex,
                )
        jawName = _("upper") if targetFdi[:1] in {"1", "2"} else _("lower")
        self._templateSupportArchStatusLabel.text = _(
            "%1 jaw only • target FDI %2 is fixed • %3 support tooth/teeth selected."
        ).replace("%1", jawName.capitalize()).replace(
            "%2", targetFdi
        ).replace("%3", str(len(selectedIds)))
        self._templateSupportArchStatusLabel.styleSheet = "color: #207227;"

    def onTemplateSupportArchButtonToggled(
        self,
        segmentId: str,
        checked: bool,
    ) -> None:
        if self._updatingTemplateUI:
            return
        listWidget = self.ui.templateSupportTeethListWidget
        for itemIndex in range(listWidget.count):
            item = listWidget.item(itemIndex)
            if str(item.data(qt.Qt.UserRole) or "") == str(segmentId):
                item.setCheckState(qt.Qt.Checked if checked else qt.Qt.Unchecked)
                return
