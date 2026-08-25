"""Extracted shared viewer and stage navigation methods; public APIs remain on DENTOWorkflowWidget."""

from __future__ import annotations

from .runtime import *


class ViewerWidgetMixin:
    @staticmethod
    def _viewControlsSettings():
        """Return workstation/application settings, never MRML case state."""

        return qt.QSettings()

    def _viewControlsSettingBool(self, key: str, default: bool) -> bool:
        value = self._viewControlsSettings().value(key, default)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    def _restoreViewControlsPaletteGeometry(self) -> None:
        if not self._viewControlsPalette or self._viewControlsPaletteGeometryRestored:
            return
        settings = self._viewControlsSettings()
        geometry = settings.value(self.VIEW_CONTROLS_GEOMETRY_SETTING)
        restored = False
        if geometry is not None:
            try:
                restored = bool(self._viewControlsPalette.restoreGeometry(geometry))
            except (TypeError, ValueError):
                restored = False
        if not restored:
            self._viewControlsPalette.resize(430, 540)
        self._viewControlsPaletteGeometryRestored = True

    def _saveViewControlsPaletteGeometry(self) -> None:
        if not self._viewControlsPalette:
            return
        settings = self._viewControlsSettings()
        settings.setValue(
            self.VIEW_CONTROLS_GEOMETRY_SETTING,
            self._viewControlsPalette.saveGeometry(),
        )
        settings.sync()

    def onOpenViewControlsPalette(self, checked: bool = False) -> None:
        del checked
        if not self._viewControlsPalette:
            return
        self._updateWorkflowViewControls()
        if self._viewControlsTabWidget:
            self._viewControlsTabWidget.currentIndex = (
                self._viewControlsElementsTabIndex
            )
        self._restoreViewControlsPaletteGeometry()
        self._viewControlsPaletteDesiredVisible = True
        settings = self._viewControlsSettings()
        settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, True)
        settings.sync()
        self._viewControlsPalette.show()
        self._viewControlsPalette.raise_()
        self._viewControlsPalette.activateWindow()

    def onViewControlsPaletteFinished(self, result: int = 0) -> None:
        del result
        self._viewControlsPaletteDesiredVisible = False
        self._saveViewControlsPaletteGeometry()
        settings = self._viewControlsSettings()
        settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, False)
        settings.sync()

    def _hideViewControlsPalette(self, preservePreference: bool = True) -> None:
        if not self._viewControlsPalette:
            return
        self._saveViewControlsPaletteGeometry()
        if not preservePreference:
            self._viewControlsPaletteDesiredVisible = False
            settings = self._viewControlsSettings()
            settings.setValue(self.VIEW_CONTROLS_VISIBLE_SETTING, False)
            settings.sync()
        self._viewControlsPalette.hide()

    def _restoreViewControlsPaletteOnEnter(self) -> None:
        if not self._viewControlsPalette:
            return
        self._viewControlsPaletteDesiredVisible = self._viewControlsSettingBool(
            self.VIEW_CONTROLS_VISIBLE_SETTING,
            False,
        )
        if self._viewControlsPaletteDesiredVisible:
            self._viewControlsPalette.show()
            self._viewControlsPalette.raise_()

    def onGuidanceToolButtonToggled(self, checked: bool) -> None:
        if self.ui.showGuidanceCheckBox.checked != bool(checked):
            self.ui.showGuidanceCheckBox.checked = bool(checked)

    def onGuidanceCheckBoxToggled(self, checked: bool) -> None:
        if not self._guidanceToolButton:
            return
        wasBlocked = self._guidanceToolButton.blockSignals(True)
        self._guidanceToolButton.checked = bool(checked)
        self._guidanceToolButton.blockSignals(wasBlocked)

    def _replaceWindowLevelSpinBoxesWithSliders(self) -> None:
        formLayout = self.ui.cbctGrayscaleDisplayFormLayout
        self.ui.cbctWindowSpinBox.visible = False
        self.ui.cbctLevelSpinBox.visible = False
        formLayout.removeWidget(self.ui.cbctWindowSpinBox)
        formLayout.removeWidget(self.ui.cbctLevelSpinBox)

        def sliderField(objectName: str, initialValue: int):
            container = qt.QWidget(self.ui.cbctGrayscaleDisplayGroupBox)
            container.objectName = f"{objectName}Field"
            layout = qt.QHBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(5)
            slider = qt.QSlider(qt.Qt.Horizontal, container)
            slider.objectName = objectName
            slider.enabled = False
            slider.focusPolicy = qt.Qt.StrongFocus
            slider.tracking = True
            slider.value = int(initialValue)
            valueLabel = qt.QLabel("--", container)
            valueLabel.objectName = f"{objectName}ValueLabel"
            valueLabel.setMinimumWidth(64)
            valueLabel.alignment = qt.Qt.AlignRight | qt.Qt.AlignVCenter
            layout.addWidget(slider, 1)
            layout.addWidget(valueLabel)
            return container, slider, valueLabel

        windowField, self._cbctWindowSlider, self._cbctWindowSliderValueLabel = (
            sliderField("cbctWindowSlider", 10)
        )
        levelField, self._cbctLevelSlider, self._cbctLevelSliderValueLabel = (
            sliderField("cbctLevelSlider", 0)
        )
        self._cbctWindowSlider.toolTip = self.ui.cbctWindowSpinBox.toolTip
        self._cbctLevelSlider.toolTip = self.ui.cbctLevelSpinBox.toolTip
        formLayout.setWidget(1, qt.QFormLayout.FieldRole, windowField)
        formLayout.setWidget(2, qt.QFormLayout.FieldRole, levelField)
        self._cbctWindowSlider.connect(
            "valueChanged(int)", self.onCbctWindowLevelSliderChanged
        )
        self._cbctLevelSlider.connect(
            "valueChanged(int)", self.onCbctWindowLevelSliderChanged
        )

    def _workflowStageEntries(self) -> list[tuple[str, object]]:
        """Return the ordered clinical/research workflow sections.

        The section widgets remain the existing CTK collapsible buttons so the
        navigation layer does not duplicate controls or MRML state.
        """

        return [
            (_("Case"), self.ui.caseCollapsibleButton),
            (_("1 · CBCT Imaging"), self.ui.imagingCollapsibleButton),
            (_("2 · AI Segmentation"), self.ui.backendCollapsibleButton),
            (_("3 · Review and Correct"), self.ui.segmentationReviewCollapsibleButton),
            (_("4A · Trajectory Planning"), self.ui.planningCollapsibleButton),
            (_("4B · Support Teeth and Draft"), self.ui.templateModelingCollapsibleButton),
            (_("4C · Guide Rails and Docks"), self.ui.targetDockingCollapsibleButton),
            (_("5A · Visible Support Surface"), self.ui.templateModelingCollapsibleButton),
            (_("5B · Shell and Guide Fusion"), self.ui.templateGuideCollapsibleButton),
            (_("5C · Verify and Export"), self.ui.templateFinalizationCollapsibleButton),
            (_("6 · Robot Placement"), self.ui.robotPlacementCollapsibleButton),
        ]

    def _setupWorkflowNavigation(self) -> None:
        """Initialize the one-visible-stage wizard over the existing controls."""

        self._updatingWorkflowNavigationUI = True
        try:
            self.ui.workflowStageComboBox.clear()
            for stageLabel, _section in self._workflowStageEntries():
                self.ui.workflowStageComboBox.addItem(stageLabel)
            self.ui.workflowStageComboBox.currentIndex = 0
            entries = self._workflowStageEntries()
            for section in {entry[1] for entry in entries}:
                active = section is entries[0][1]
                section.visible = active
                section.collapsed = not active
            self.ui.assistedTrajectoryCollapsibleButton.collapsed = True
            self.ui.assistedTrajectoryCollapsibleButton.visible = False
        finally:
            self._updatingWorkflowNavigationUI = False

        self.ui.workflowStageComboBox.connect(
            "currentIndexChanged(int)",
            self.onWorkflowStageChanged,
        )
        self.ui.previousWorkflowStageButton.connect(
            "clicked(bool)",
            self.onPreviousWorkflowStage,
        )
        self.ui.nextWorkflowStageButton.connect(
            "clicked(bool)",
            self.onNextWorkflowStage,
        )
        self.ui.showGuidanceCheckBox.connect(
            "toggled(bool)",
            self.onShowGuidanceToggled,
        )
        self.ui.showBackendLogCheckBox.connect(
            "toggled(bool)",
            self.onShowBackendLogToggled,
        )
        self.ui.workflowViewPresetComboBox.connect(
            "currentIndexChanged(int)",
            self.onWorkflowViewPresetChanged,
        )
        self.ui.workflowViewElementsListWidget.connect(
            "itemChanged(QListWidgetItem*)",
            self.onWorkflowViewElementChanged,
        )
        self.ui.frameWorkflowViewButton.connect(
            "clicked(bool)",
            self.onFrameWorkflowView,
        )
        self.ui.restoreWorkflowViewButton.connect(
            "clicked(bool)",
            self.onRestoreWorkflowView,
        )
        connectedSections = set()
        for _index, (_stageLabel, section) in enumerate(self._workflowStageEntries()):
            if section in connectedSections:
                continue
            connectedSections.add(section)
            section.connect(
                "contentsCollapsed(bool)",
                lambda collapsed, activeSection=section: self._onWorkflowSectionCollapsed(
                    activeSection, collapsed
                ),
            )
        self._setGuidanceVisible(False)
        self._updateWorkflowNavigationButtons()
        self._setWorkflowViewAvailability(False)

    @staticmethod
    def _normalizedTrajectoryPlacementMode(mode: str) -> str:
        return "Assisted" if str(mode).strip() == "Assisted" else "Manual"

    def _trajectoryPlacementMode(self) -> str:
        if not self._parameterNode:
            return "Manual"
        return self._normalizedTrajectoryPlacementMode(
            self._parameterNode.trajectoryPlacementMode
        )

    def _updateTrajectoryPlacementModeControls(self) -> None:
        if not hasattr(self, "ui"):
            return
        mode = self._trajectoryPlacementMode()
        comboBox = self.ui.trajectoryPlacementModeComboBox
        self._updatingPlanningUI = True
        try:
            selectedIndex = comboBox.findData(mode)
            comboBox.currentIndex = max(int(selectedIndex), 0)
            manualVisible = mode == "Manual"
            for widget in (
                self.ui.createTrajectoryButton,
                self.ui.placeTrajectoryButton,
                self.ui.undoTrajectoryPointButton,
                self.ui.resetTrajectoryButton,
            ):
                widget.visible = manualVisible
            stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
            assistedVisible = mode == "Assisted" and stageIndex == 4
            self.ui.assistedTrajectoryCollapsibleButton.visible = assistedVisible
            if assistedVisible:
                self.ui.assistedTrajectoryCollapsibleButton.collapsed = False
        finally:
            self._updatingPlanningUI = False

    def onTrajectoryPlacementModeChanged(self, index: int) -> None:
        if self._updatingPlanningUI or not self._parameterNode:
            return
        mode = self.ui.trajectoryPlacementModeComboBox.itemData(int(index))
        normalizedMode = self._normalizedTrajectoryPlacementMode(mode)
        if self._parameterNode.trajectoryPlacementMode != normalizedMode:
            self._parameterNode.trajectoryPlacementMode = normalizedMode
        self._updateTrajectoryPlacementModeControls()
        self._updatePlanning()

    def _guidanceWidgets(self) -> list[object]:
        widgetNames = (
            "introLabel",
            "dicomInstructionLabel",
            "backendDescriptionLabel",
            "runArtifactsExplanationLabel",
            "segmentationSafetyLabel",
            "segmentationReviewDescriptionLabel",
            "segmentationReviewSafetyLabel",
            "planningDescriptionLabel",
            "planningSafetyLabel",
            "assistedTrajectoryDescriptionLabel",
            "assistedTrajectorySafetyLabel",
            "targetDockingDescriptionLabel",
            "targetDockingSafetyLabel",
            "templateModelingDescriptionLabel",
            "templateModelingSafetyLabel",
            "templateGuideDescriptionLabel",
            "templateDockingFusionDescriptionLabel",
            "templateGuideSafetyLabel",
            "finalVerificationDescriptionLabel",
            "finalVerificationSafetyLabel",
        )
        return [
            getattr(self.ui, widgetName)
            for widgetName in widgetNames
            if hasattr(self.ui, widgetName)
        ]

    def _setGuidanceVisible(self, visible: bool) -> None:
        for widget in self._guidanceWidgets():
            widget.visible = bool(visible)

    def onShowGuidanceToggled(self, visible: bool) -> None:
        self._setGuidanceVisible(visible)

    def onShowBackendLogToggled(self, visible: bool) -> None:
        self.ui.backendLogTextEdit.visible = bool(visible)

    def _workflowViewSupportSegmentIds(self) -> list[str]:
        if not self._parameterNode or not self.logic:
            return []
        try:
            supportIds = self.logic.decodeTemplateSupportSegmentIds(
                self._parameterNode.templateSupportToothSegmentIdsJson
            )
        except ValueError:
            supportIds = []
        sourceModel = self._parameterNode.draftTemplateSupportModel
        if self.logic.isDraftTemplateSupportModelNode(sourceModel):
            try:
                supportIds = self.logic.getDraftTemplateSupportModelSummary(
                    sourceModel
                )["supportSegmentIds"]
            except (RuntimeError, ValueError, json.JSONDecodeError):
                pass
        targetId = self._parameterNode.targetToothSegmentId
        return [
            segmentId
            for segmentId in supportIds
            if segmentId and segmentId != targetId
        ]

    def _workflowManagedDisplayNodes(self) -> list:
        """Return every user-facing displayable so presets never leave stale objects."""

        nodesById = {}
        if self._parameterNode:
            for fieldName in (
                "targetToothBoundsRoi",
                "trajectoryLine",
                "assistedTrajectoryEntries",
                "targetDockingReferencePlane",
                "targetDockingAssemblyModel",
                "draftTemplateSupportModel",
                "templateSupportBoundaryCurve",
                "templateSupportBoundaryPlane",
                "visibleTemplateSupportModel",
                "templateInsertionDirection",
                "templateUndercutSurfaceModel",
                "templateUndercutBlockoutModel",
                "patientContactShellModel",
                "templateDockingAssemblyModel",
                "templateDockingClearanceModel",
                "templateDockingReinforcementModel",
                "templateDockingChannelsModel",
                "finalPrintableTemplateModel",
                "templateShellRoi",
                "researchTemplateShellModel",
                "researchTemplateSleeveModel",
                "templateTrimPlane",
                "templateTrimCurve",
                "finalizedTemplateShellModel",
                "robotBaseTransform",
                "robotMountPlane",
                "draftPhantomSkullModel",
                "draftPhantomMandibleModel",
                "draftJawLandmarks",
                "draftJawGapLine",
            ):
                node = getattr(self._parameterNode, fieldName, None)
                if node and node.GetID() and node.IsA("vtkMRMLDisplayableNode"):
                    nodesById[node.GetID()] = node
        ownershipAttributes = (
            "DENTOBOT.TrajectoryRole",
            "DENTOBOT.MarkupsRole",
            "DENTOBOT.ModelRole",
            "DENTOBOT.BoundsRole",
        )
        for node in slicer.util.getNodesByClass("vtkMRMLDisplayableNode"):
            if node.IsA("vtkMRMLSegmentationNode"):
                continue
            hideFromEditors = getattr(node, "GetHideFromEditors", None)
            if hideFromEditors and hideFromEditors():
                continue
            if not node.GetDisplayNode():
                try:
                    node.CreateDefaultDisplayNodes()
                except Exception:
                    continue
            if node.GetID() and node.GetDisplayNode():
                nodesById[node.GetID()] = node
            if any(node.GetAttribute(attribute) for attribute in ownershipAttributes):
                nodesById[node.GetID()] = node
        if self.logic:
            for node in (
                *self.logic.robotModelNodes(),
                *self.logic.draftPhantomModelNodes(),
            ):
                if node and node.GetID():
                    nodesById[node.GetID()] = node
        try:
            ros_robot = find_ros2_robot_by_name("dentobot")
        except Exception:
            ros_robot = None
        if ros_robot:
            for index in range(ros_robot.GetNumberOfNodeReferences("model")):
                model = ros_robot.GetNthNodeReference("model", index)
                if model and model.GetID() and model.IsA("vtkMRMLDisplayableNode"):
                    nodesById[model.GetID()] = model
        return list(nodesById.values())

    def _workflowCuratedViewEntries(self, stageIndex: int) -> list[dict]:
        if not self._parameterNode or not self.logic or stageIndex < 4:
            return []
        if stageIndex == 10:
            return self._step6WorkflowViewEntries()
        segmentationNode = self._parameterNode.teethSegmentation
        targetId = self._parameterNode.targetToothSegmentId
        supportIds = self._workflowViewSupportSegmentIds()
        entries = []

        def addSegments(key, label, segmentIds, category, stages) -> None:
            if stageIndex not in stages or not segmentationNode:
                return
            segmentation = segmentationNode.GetSegmentation()
            validIds = [
                segmentId
                for segmentId in segmentIds
                if segmentation.GetSegment(segmentId)
            ]
            if validIds:
                entries.append(
                    {
                        "key": key,
                        "label": label,
                        "kind": "segments",
                        "segmentIds": validIds,
                        "category": category,
                    }
                )

        def addNode(key, label, node, category, stages) -> None:
            if (
                stageIndex not in stages
                or not node
                or not node.GetID()
                or not node.GetDisplayNode()
            ):
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )

        allStageIndices = {4, 5, 6, 7, 8, 9}
        if segmentationNode and targetId:
            targetLabel = targetId
            targetRecord = self._targetToothRecordsById.get(targetId)
            if targetRecord:
                targetLabel = targetRecord["displayName"]
            addSegments(
                "segments:target",
                _("[Mask] Target tooth — %1").replace("%1", targetLabel),
                [targetId],
                "target_mask",
                allStageIndices,
            )
            targetFdi = (
                str(targetRecord.get("fdiNumber") or "")
                if targetRecord
                else ""
            )
            if targetFdi:
                try:
                    detailIds = [
                        record["segmentId"]
                        for record in self.logic.getSegmentationReviewRecords(
                            segmentationNode
                        )
                        if record.get("fdiNumber") == targetFdi
                        and record.get("category") == "Pulp and root canals"
                    ]
                except ValueError:
                    detailIds = []
                addSegments(
                    "segments:targetDetail",
                    _("[Mask] Target pulp / root canal (%1)").replace(
                        "%1", str(len(detailIds))
                    ),
                    detailIds,
                    "target_detail",
                    {4},
                )
        addSegments(
            "segments:support",
            _("[Masks] Selected support teeth (%1)").replace(
                "%1", str(len(supportIds))
            ),
            supportIds,
            "support_mask",
            {5, 6, 7, 8, 9},
        )
        if segmentationNode:
            allSegmentIds = vtk.vtkStringArray()
            segmentationNode.GetSegmentation().GetSegmentIDs(allSegmentIds)
            subjectIds = {targetId, *supportIds}
            otherIds = [
                allSegmentIds.GetValue(index)
                for index in range(allSegmentIds.GetNumberOfValues())
                if allSegmentIds.GetValue(index) not in subjectIds
            ]
            addSegments(
                "segments:other",
                _("[Masks] Other segmented anatomy (%1)").replace(
                    "%1", str(len(otherIds))
                ),
                otherIds,
                "other_mask",
                allStageIndices,
            )

        addNode(
            "node:targetBounds",
            _("[4A] Target bounds box"),
            self._parameterNode.targetToothBoundsRoi,
            "bounds",
            allStageIndices,
        )
        targetTrajectories = []
        if segmentationNode and targetId:
            targetTrajectories = self.logic.dentobotTrajectoriesForTarget(
                segmentationNode,
                targetId,
            )
        for trajectoryNode in targetTrajectories:
            selectedSuffix = (
                _(" — selected")
                if trajectoryNode is self._parameterNode.trajectoryLine
                else ""
            )
            addNode(
                f"trajectory:{trajectoryNode.GetID()}",
                _("[4A] %1%2")
                .replace("%1", trajectoryNode.GetName() or _("Trajectory"))
                .replace("%2", selectedSuffix),
                trajectoryNode,
                "trajectory",
                allStageIndices,
            )
        addNode(
            "node:assistedEntries",
            _("[4A] Assisted crown entry points"),
            self._parameterNode.assistedTrajectoryEntries,
            "assisted",
            {4},
        )
        addNode(
            "node:targetDockingPlane",
            _("[4C] Occlusal reference plane"),
            self._parameterNode.targetDockingReferencePlane,
            "target_docking",
            {6, 7, 8, 9},
        )
        addNode(
            "node:targetDockingAssembly",
            _("[4C] Guide rails / four docks"),
            self._parameterNode.targetDockingAssemblyModel,
            "target_docking",
            {6, 7, 8, 9},
        )
        dockingAssembly = self._parameterNode.targetDockingAssemblyModel
        if dockingAssembly:
            role = self.logic.TARGET_DOCKING_MEASUREMENT_REFERENCE_ROLE
            for index in range(dockingAssembly.GetNumberOfNodeReferences(role)):
                measurementNode = dockingAssembly.GetNthNodeReference(role, index)
                addNode(
                    f"targetDockingMeasurement:{measurementNode.GetID()}"
                    if measurementNode
                    else f"targetDockingMeasurement:{index}",
                    measurementNode.GetName()
                    if measurementNode
                    else _("[4B] Dock measurement"),
                    measurementNode,
                    "target_docking_measurement",
                    {6, 7, 8, 9},
                )
        addNode(
            "node:draftSupport",
            _("[4B] Complete support-tooth draft"),
            self._parameterNode.draftTemplateSupportModel,
            "draft_support",
            {5, 6, 7},
        )
        addNode(
            "node:supportBoundary",
            _("[5A] Support boundary"),
            self._parameterNode.templateSupportBoundaryCurve,
            "support_boundary",
            {7, 8},
        )
        addNode(
            "node:supportPlane",
            _("[5A] Automatic support plane"),
            self._parameterNode.templateSupportBoundaryPlane,
            "support_plane",
            {7},
        )
        addNode(
            "node:visibleSupport",
            _("[5A] Visible support preview"),
            self._parameterNode.visibleTemplateSupportModel,
            "visible_support",
            {7, 8, 9},
        )
        addNode(
            "node:insertionDirection",
            _("[5B] Insertion direction"),
            self._parameterNode.templateInsertionDirection,
            "insertion",
            {8},
        )
        addNode(
            "node:undercut",
            _("[5B] Undercut preview"),
            self._parameterNode.templateUndercutSurfaceModel,
            "undercut",
            {8},
        )
        addNode(
            "node:blockout",
            _("[5B] Directional blockout"),
            self._parameterNode.templateUndercutBlockoutModel,
            "blockout",
            {8},
        )
        addNode(
            "node:patientShell",
            _("[5B] Patient-contact shell"),
            self._parameterNode.patientContactShellModel,
            "patient_shell",
            {8, 9},
        )
        for keySuffix, label, node in (
            (
                "dockingFusion",
                _("[5B] Integrated docking assembly"),
                self._parameterNode.templateDockingAssemblyModel,
            ),
            (
                "dockingClearance",
                _("[5B] Docking clearance"),
                self._parameterNode.templateDockingClearanceModel,
            ),
            (
                "reinforcement",
                _("[5B] Shell reinforcement"),
                self._parameterNode.templateDockingReinforcementModel,
            ),
            (
                "channels",
                _("[5B] Drill / dock channels"),
                self._parameterNode.templateDockingChannelsModel,
            ),
        ):
            addNode(
                f"node:{keySuffix}",
                label,
                node,
                "final_aux",
                {8, 9},
            )
        addNode(
            "node:finalTemplate",
            _("[5C] Final printable template"),
            self._parameterNode.finalPrintableTemplateModel,
            "final",
            {8, 9},
        )
        return entries

    def _workflowViewEntries(self, stageIndex: int) -> list[dict]:
        """Return grouped masks and existing display objects without scene mutation."""

        if not self._parameterNode or not self.logic:
            return []
        curated = list(self._workflowCuratedViewEntries(stageIndex))
        entries = list(curated)

        for segmentationNode in slicer.util.getNodesByClass(
            "vtkMRMLSegmentationNode"
        ):
            segmentation = segmentationNode.GetSegmentation()
            if not segmentation:
                continue
            segmentIds = vtk.vtkStringArray()
            segmentation.GetSegmentIDs(segmentIds)
            records = []
            for segmentIndex in range(segmentIds.GetNumberOfValues()):
                segmentId = segmentIds.GetValue(segmentIndex)
                segment = segmentation.GetSegment(segmentId)
                if not segment:
                    continue
                records.append(
                    {
                        "segmentId": segmentId,
                        **self.logic.describeSegmentForReview(
                            segment.GetName() or segmentId
                        ),
                    }
                )
            for groupKey, groupedIds in group_segmentation_records_detailed(
                records
            ).items():
                if not groupedIds:
                    continue
                authoritative = (
                    segmentationNode is self._parameterNode.teethSegmentation
                )
                entries.append(
                    {
                        "key": (
                            f"segments:anatomy:{groupKey}:{segmentationNode.GetID()}"
                        ),
                        "label": _("[%1] %2 (%3) — %4")
                        .replace(
                            "%1",
                            _("Dental mask group")
                            if authoritative
                            else _("Other scene mask group"),
                        )
                        .replace(
                            "%2",
                            _(DETAILED_ANATOMY_GROUP_LABELS[groupKey]),
                        )
                        .replace("%3", str(len(groupedIds)))
                        .replace(
                            "%4",
                            segmentationNode.GetName() or _("Segmentation"),
                        ),
                        "kind": "segments",
                        "segmentationNode": segmentationNode,
                        "segmentIds": groupedIds,
                        "category": (
                            DETAILED_ANATOMY_GROUP_CATEGORY[groupKey]
                            if authoritative
                            else "scene_mask"
                        ),
                        "anatomyGroup": groupKey,
                        "anatomyScopes": (
                            anatomy_scopes_for_group(groupKey)
                            if authoritative
                            else frozenset()
                        ),
                    }
                )

        representedNodeIds = set()
        for entry in entries:
            if entry["kind"] == "node" and entry.get("node"):
                representedNodeIds.add(entry["node"].GetID())
            elif entry["kind"] == "nodes":
                representedNodeIds.update(
                    node.GetID() for node in entry["nodes"] if node and node.GetID()
                )
        for node in self._workflowManagedDisplayNodes():
            if node.GetID() in representedNodeIds:
                continue
            classLabel = node.GetClassName().replace("vtkMRML", "").replace("Node", "")
            scalarVolume = node.IsA("vtkMRMLScalarVolumeNode")
            category = (
                "case_volume"
                if scalarVolume and node is self._parameterNode.inputVolume
                else "scene_volume"
                if scalarVolume
                else "scene_element"
            )
            labelPrefix = (
                _("Case CBCT")
                if category == "case_volume"
                else _("Other scene volume")
                if category == "scene_volume"
                else _("Scene/%1").replace("%1", classLabel)
            )
            entries.append(
                {
                    "key": f"scene:{node.GetID()}",
                    "label": _("[%1] %2")
                    .replace("%1", labelPrefix)
                    .replace("%2", node.GetName() or node.GetID()),
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )
        volumeRenderingLogic = (
            slicer.modules.volumerendering.logic()
            if hasattr(slicer.modules, "volumerendering")
            else None
        )
        if volumeRenderingLogic:
            for volumeNode in slicer.util.getNodesByClass("vtkMRMLScalarVolumeNode"):
                try:
                    renderingDisplay = (
                        volumeRenderingLogic.GetFirstVolumeRenderingDisplayNode(
                            volumeNode
                        )
                    )
                except Exception:
                    renderingDisplay = None
                if renderingDisplay:
                    entries.append(
                        {
                            "key": f"volumeRendering:{volumeNode.GetID()}",
                            "label": _("[Volume rendering — not a mask] %1").replace(
                                "%1", volumeNode.GetName() or volumeNode.GetID()
                            ),
                            "kind": "volume_rendering",
                            "node": volumeNode,
                            "displayNode": renderingDisplay,
                            "category": (
                                "case_volume_3d"
                                if volumeNode is self._parameterNode.inputVolume
                                else "scene_volume_rendering"
                            ),
                        }
                    )
        return entries

    def _step6WorkflowViewEntries(self) -> list[dict]:
        """Step 6 Elements list: case package, phantom, robot, mount — not the full 4A–5C dump."""
        entries: list[dict] = []
        parameterNode = self._parameterNode
        segmentationNode = parameterNode.teethSegmentation
        targetId = parameterNode.targetToothSegmentId

        def addSegments(key, label, segmentIds, category) -> None:
            if not segmentationNode:
                return
            segmentation = segmentationNode.GetSegmentation()
            validIds = [
                segmentId
                for segmentId in segmentIds
                if segmentation.GetSegment(segmentId)
            ]
            if validIds:
                entries.append(
                    {
                        "key": key,
                        "label": label,
                        "kind": "segments",
                        "segmentIds": validIds,
                        "category": category,
                    }
                )

        def addNode(key, label, node, category) -> None:
            if not node or not node.GetID():
                return
            if not node.GetDisplayNode():
                try:
                    node.CreateDefaultDisplayNodes()
                except Exception:
                    return
            if not node.GetDisplayNode():
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "node",
                    "node": node,
                    "category": category,
                }
            )

        def addNodes(key, label, nodes, category) -> None:
            valid = []
            for node in nodes:
                if not node or not node.GetID():
                    continue
                if not node.GetDisplayNode():
                    try:
                        node.CreateDefaultDisplayNodes()
                    except Exception:
                        continue
                if node.GetDisplayNode():
                    valid.append(node)
            if not valid:
                return
            entries.append(
                {
                    "key": key,
                    "label": label,
                    "kind": "nodes",
                    "nodes": valid,
                    "category": category,
                }
            )

        if segmentationNode and targetId:
            targetLabel = targetId
            targetRecord = self._targetToothRecordsById.get(targetId)
            if targetRecord:
                targetLabel = targetRecord["displayName"]
            addSegments(
                "segments:target",
                _("[Mask] Target tooth — %1").replace("%1", targetLabel),
                [targetId],
                "target_mask",
            )
        if parameterNode.trajectoryLine:
            addNode(
                "node:step6Trajectory",
                _("[4A] Selected trajectory"),
                parameterNode.trajectoryLine,
                "trajectory",
            )
        addNode(
            "node:step6Volume",
            _("[1] CBCT volume"),
            parameterNode.inputVolume,
            "case_volume",
        )
        addNode(
            "node:step6Bounds",
            _("[4A] Target tooth bounds"),
            parameterNode.targetToothBoundsRoi,
            "bounds",
        )
        addNode(
            "node:step6Docks",
            _("[4C] Guide rails / docks"),
            parameterNode.targetDockingAssemblyModel,
            "target_docking",
        )
        addNode(
            "node:step6Template",
            _("[5C] Final printable template"),
            parameterNode.finalPrintableTemplateModel,
            "final",
        )
        addNode(
            "node:step6CaseLowerJaw",
            _("[Step 6.0A] Opened lower-jaw planning surface"),
            parameterNode.step6OpenedLowerJawModel,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseOpenedTargetGeometry",
            _("[Step 6.0A] Opened target-attached geometry"),
            parameterNode.step6OpenedTargetGeometryModel,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseOpenedTrajectory",
            _("[Step 6.0A] Opened Entry-to-Target"),
            parameterNode.step6OpenedTrajectoryLine,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseJawLandmarks",
            _("[Step 6.0A] Case TMJ/incisor landmarks"),
            parameterNode.step6CaseJawLandmarks,
            "case_jaw_opening",
        )
        addNode(
            "node:step6CaseJawGap",
            _("[Step 6.0A] Case incisor gap"),
            parameterNode.step6CaseJawGapLine,
            "case_jaw_opening",
        )
        addNodes(
            "nodes:step6Phantom",
            _("[Step 6] Draft phantom"),
            self.logic.draftPhantomModelNodes(),
            "phantom",
        )
        addNode(
            "node:step6JawLandmarks",
            _("[Step 6] Jaw landmarks"),
            parameterNode.draftJawLandmarks,
            "phantom_landmarks",
        )
        addNode(
            "node:step6JawGap",
            _("[Step 6] Incisor gap line"),
            parameterNode.draftJawGapLine,
            "phantom_landmarks",
        )
        addNode(
            "node:step6Mount",
            _("[Step 6] Mount plane"),
            parameterNode.robotMountPlane,
            "robot_mount",
        )
        addNode(
            "node:step6ForeheadProxy",
            _("[Step 6] Forehead proxy — unregistered / visualization only"),
            parameterNode.robotForeheadProxyModel,
            "forehead_proxy",
        )
        addNodes(
            "nodes:step6MrmlRobot",
            _("[Step 6] MRML robot links"),
            self.logic.robotModelNodes(),
            "robot_mrml",
        )
        try:
            ros_robot = find_ros2_robot_by_name("dentobot")
        except Exception:
            ros_robot = None
        if ros_robot is not None:
            ros_models = [
                ros_robot.GetNthNodeReference("model", index)
                for index in range(ros_robot.GetNumberOfNodeReferences("model"))
            ]
            addNodes(
                "nodes:step6RosRobot",
                _("[Step 6] ROS robot"),
                ros_models,
                "robot_ros",
            )
            goal_models = [
                ros_robot.GetNthNodeReference("goal_model", index)
                for index in range(ros_robot.GetNumberOfNodeReferences("goal_model"))
            ]
            addNodes(
                "nodes:step6GoalRobot",
                _("[Step 6] Goal robot"),
                goal_models,
                "robot_goal",
            )
        return entries

    @staticmethod
    def _workflowViewPresetCategories(presetKey: str) -> set[str] | None:
        categories = {
            "cbct_slices": {"case_volume"},
            "teeth_upper_both": {"upper_teeth"},
            "teeth_lower_both": {"lower_teeth"},
            "teeth_all_both": {"upper_teeth", "lower_teeth"},
            "all_masks": {
                "upper_teeth",
                "lower_teeth",
                "pulp_root_canals",
                "neural_canals",
                "jaws",
                "sinuses_airway",
                "restorations_implants",
                "other_mask",
            },
            "target_only": {"target_mask"},
            "trajectory_only": {
                "target_mask",
                "target_detail",
                "trajectory",
            },
            "plan": {"target_mask", "bounds", "trajectory", "assisted"},
            "support_masks": {"target_mask", "support_mask"},
            "support_design": {
                "target_mask",
                "support_mask",
                "draft_support",
                "support_boundary",
                "support_plane",
                "visible_support",
            },
            "docks_only": {"target_docking", "target_docking_measurement"},
            "undercut_analysis": {
                "visible_support",
                "insertion",
                "undercut",
                "blockout",
            },
            "shell_only": {"patient_shell"},
            "shell_guides": {
                "patient_shell",
                "trajectory",
                "target_docking",
                "final_aux",
            },
            "final_only": {"final"},
            "robot_mount_only": {
                "robot_mrml", "robot_ros", "robot_goal", "robot_mount", "forehead_proxy"
            },
            "case_package": {
                "case_volume",
                "target_mask",
                "bounds",
                "trajectory",
                "target_docking",
                "final",
                "case_jaw_opening",
            },
            "phantom_only": {"phantom", "phantom_landmarks"},
        }
        return categories.get(presetKey)

    def _workflowViewRecommendedCategories(self, stageIndex: int) -> set[str]:
        categories = recommended_view_categories(stageIndex)
        if stageIndex == 7:
            if not self._parameterNode.visibleTemplateSupportModel:
                categories.add("draft_support")
            return categories
        if stageIndex == 8:
            if self._parameterNode.finalPrintableTemplateModel:
                return {"final"}
            return categories
        if stageIndex == 9:
            return (
                {"final"}
                if self._parameterNode.finalPrintableTemplateModel
                else categories
            )
        if stageIndex == 10:
            ros_active = self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
            robot_category = {"robot_ros"} if ros_active else {"robot_mrml"}
            kind = self._step6SceneKind()
            if kind == "phantom":
                categories = {"phantom", "robot_mount", *robot_category}
                landmarks = self._parameterNode.draftJawLandmarks
                if landmarks is None or landmarks.GetNumberOfDefinedControlPoints() < 4:
                    categories.add("phantom_landmarks")
                return categories
            return {
                "case_volume",
                "case_volume_3d",
                "target_mask",
                "bounds",
                "trajectory",
                "target_docking",
                "final",
                "case_jaw_opening",
                "robot_mount",
                "forehead_proxy",
                *robot_category,
            }
        return categories

    def _workflowViewPresetDefinitions(
        self,
        stageIndex: int,
        entries: list[dict],
    ) -> list[tuple[str, str]]:
        categories = {entry["category"] for entry in entries}
        definitions = [
            ("scene", _("Current scene visibility (unchanged)")),
            ("recommended", _("Recommended for this step")),
        ]
        if "case_volume" in categories:
            definitions.append(("cbct_slices", _("CBCT slices only")))
        if "upper_teeth" in categories:
            definitions.append(
                ("teeth_upper_both", _("Upper teeth masks — 2D + 3D"))
            )
        if "lower_teeth" in categories:
            definitions.append(
                ("teeth_lower_both", _("Lower teeth masks — 2D + 3D"))
            )
        if categories & {"upper_teeth", "lower_teeth"}:
            definitions.append(
                ("teeth_all_both", _("All teeth masks — 2D + 3D"))
            )
        if categories & {
            "pulp_root_canals",
            "neural_canals",
            "jaws",
            "sinuses_airway",
            "restorations_implants",
            "other_mask",
        }:
            definitions.append(("all_masks", _("All segmentation masks")))
        if "target_mask" in categories:
            definitions.append(("target_only", _("Target tooth mask only")))
        if stageIndex == 4 and "trajectory" in categories:
            definitions.append(
                ("trajectory_only", _("Selected trajectory context only"))
            )
        if categories & {"trajectory", "bounds", "assisted"}:
            definitions.append(("plan", _("Target + trajectory planning")))
        if "support_mask" in categories:
            definitions.append(("support_masks", _("Target + support masks only")))
        if categories & {
            "support_boundary",
            "support_plane",
            "visible_support",
        }:
            definitions.append(("support_design", _("Support-surface design")))
        if "target_docking" in categories:
            definitions.append(("docks_only", _("Guide rails / docks only")))
        if categories & {"undercut", "blockout", "insertion"}:
            definitions.append(("undercut_analysis", _("Undercut analysis only")))
        if "patient_shell" in categories:
            definitions.append(("shell_only", _("Patient-contact shell only")))
            definitions.append(("shell_guides", _("Shell + trajectories + guides")))
        if "final" in categories:
            definitions.append(("final_only", _("Final printable template only")))
        if stageIndex == 10:
            definitions.append(("robot_mount_only", _("Robot + mount only")))
            if categories & {"target_mask", "trajectory", "target_docking", "final"}:
                definitions.append(
                    ("case_package", _("Case planning package"))
                )
            if "phantom" in categories:
                definitions.append(("phantom_only", _("Phantom only")))
        definitions.extend(
            (
                ("all", _("All elements available in this step")),
                ("custom", _("Custom element selection")),
            )
        )
        return definitions

    def _workflowViewKeysForPreset(
        self,
        presetKey: str,
        entries: list[dict],
        stageIndex: int,
    ) -> set[str]:
        if presetKey == "all":
            return {entry["key"] for entry in entries}
        if presetKey == "recommended":
            categories = self._workflowViewRecommendedCategories(stageIndex)
        else:
            categories = self._workflowViewPresetCategories(presetKey) or set()
        visibleKeys = {
            entry["key"]
            for entry in entries
            if entry["category"] in categories
        }
        if (
            self._parameterNode
            and not self._parameterNode.targetDockingMeasurementsVisible
        ):
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and entry["category"] != "target_docking_measurement"
            }
        if presetKey == "trajectory_only":
            selectedTrajectory = (
                self._parameterNode.trajectoryLine
                if self._parameterNode
                else None
            )
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and (
                    entry["category"] != "trajectory"
                    or entry.get("node") is selectedTrajectory
                )
            }
        if (
            presetKey == "recommended"
            and stageIndex == 4
            and not self._parameterNode.assistedTrajectoryEntries
        ):
            selectedTrajectory = (
                self._parameterNode.trajectoryLine
                if self._parameterNode
                else None
            )
            visibleKeys = {
                entry["key"]
                for entry in entries
                if entry["key"] in visibleKeys
                and (
                    entry["category"] != "trajectory"
                    or entry.get("node") is selectedTrajectory
                )
            }
        return visibleKeys

    def _workflowViewEntryCheckState(self, entry: dict) -> int:
        if entry["kind"] == "volume_rendering":
            return (
                qt.Qt.Checked
                if entry["displayNode"].GetVisibility()
                else qt.Qt.Unchecked
            )
        if entry["kind"] == "node":
            displayNode = entry["node"].GetDisplayNode()
            return (
                qt.Qt.Checked
                if displayNode and displayNode.GetVisibility()
                else qt.Qt.Unchecked
            )
        if entry["kind"] == "nodes":
            states = []
            for node in entry["nodes"]:
                displayNode = node.GetDisplayNode() if node else None
                states.append(bool(displayNode and displayNode.GetVisibility()))
            if states and all(states):
                return qt.Qt.Checked
            if any(states):
                return qt.Qt.PartiallyChecked
            return qt.Qt.Unchecked
        segmentationNode = entry.get("segmentationNode") or self._parameterNode.teethSegmentation
        displayNode = segmentationNode.GetDisplayNode() if segmentationNode else None
        if not displayNode or not displayNode.GetVisibility():
            return qt.Qt.Unchecked
        states = [
            bool(displayNode.GetSegmentVisibility(segmentId))
            for segmentId in entry["segmentIds"]
        ]
        if states and all(states):
            return qt.Qt.Checked
        if any(states):
            return qt.Qt.PartiallyChecked
        return qt.Qt.Unchecked

    @staticmethod
    def _workflowAdvancedTreeGroup(entry: dict) -> tuple[str, str]:
        category = entry["category"]
        anatomyGroup = str(entry.get("anatomyGroup") or "")
        if anatomyGroup:
            region = (
                "Upper jaw"
                if anatomyGroup.startswith("upper_")
                else "Lower jaw"
                if anatomyGroup.startswith("lower_")
                else "Other / adjacent anatomy"
            )
            return "Authoritative anatomy", region
        if category == "scene_mask":
            return "Other scene data", "Other segmentations"
        if category in {
            "target_mask",
            "target_detail",
            "bounds",
            "trajectory",
            "assisted",
        }:
            return "Planning objects", "Trajectory planning"
        if category in {
            "support_mask",
            "draft_support",
            "support_boundary",
            "support_plane",
            "visible_support",
            "insertion",
            "undercut",
            "blockout",
            "patient_shell",
            "target_docking",
            "target_docking_measurement",
            "final_aux",
            "final",
        }:
            return "Guide-design objects", "Guide and template"
        if category in {
            "robot_mrml",
            "robot_ros",
            "robot_goal",
            "robot_mount",
            "forehead_proxy",
            "phantom",
            "phantom_landmarks",
            "case_jaw_opening",
        }:
            return "Robot simulation objects", "Step 6 scene"
        if category in {
            "case_volume",
            "case_volume_3d",
            "scene_volume",
            "scene_volume_rendering",
        }:
            return "CBCT and rendering", "Volumes and renderers"
        return "Other scene data", "Displayable nodes"

    def _workflowSegmentLeafEntry(
        self,
        parentEntry: dict,
        segmentId: str,
    ) -> dict:
        segmentationNode = (
            parentEntry.get("segmentationNode")
            or self._parameterNode.teethSegmentation
        )
        return {
            **parentEntry,
            "key": f"segment:{segmentationNode.GetID()}:{segmentId}",
            "label": segmentId,
            "segmentIds": [segmentId],
            "parentGroupKey": parentEntry["key"],
        }

    def _populateWorkflowAdvancedTree(
        self,
        entries: list[dict],
        stageIndex: int,
    ) -> None:
        tree = self._workflowAdvancedTree
        if not tree:
            return
        tree.clear()
        recommendedCategories = self._workflowViewRecommendedCategories(stageIndex)
        rootOrder = (
            "Authoritative anatomy",
            "Planning objects",
            "Guide-design objects",
            "Robot simulation objects",
            "CBCT and rendering",
            "Other scene data",
        )
        roots: dict[str, object] = {}
        subgroups: dict[tuple[str, str], object] = {}
        for title in rootOrder:
            root = qt.QTreeWidgetItem(tree)
            root.setText(0, _(title))
            root.setFlags(
                root.flags()
                | qt.Qt.ItemIsUserCheckable
                | qt.Qt.ItemIsAutoTristate
            )
            root.setCheckState(0, qt.Qt.Unchecked)
            roots[title] = root

        sortedEntries = sorted(
            entries,
            key=lambda entry: (
                entry["category"] not in recommendedCategories,
                self._workflowAdvancedTreeGroup(entry),
                entry["label"].lower(),
            ),
        )
        for entry in sortedEntries:
            rootTitle, subgroupTitle = self._workflowAdvancedTreeGroup(entry)
            root = roots[rootTitle]
            subgroupKey = (rootTitle, subgroupTitle)
            subgroup = subgroups.get(subgroupKey)
            if subgroup is None:
                subgroup = qt.QTreeWidgetItem(root)
                subgroup.setText(0, _(subgroupTitle))
                subgroup.setFlags(
                    subgroup.flags()
                    | qt.Qt.ItemIsUserCheckable
                    | qt.Qt.ItemIsAutoTristate
                )
                subgroup.setCheckState(0, qt.Qt.Unchecked)
                subgroups[subgroupKey] = subgroup
            item = qt.QTreeWidgetItem(subgroup)
            item.setText(0, entry["label"])
            item.setData(0, qt.Qt.UserRole, entry["key"])
            item.setFlags(item.flags() | qt.Qt.ItemIsUserCheckable)
            item.setCheckState(0, self._workflowViewEntryCheckState(entry))
            relevant = entry["category"] in recommendedCategories
            if relevant:
                item.setBackground(0, qt.QColor(225, 242, 250))
                font = item.font(0)
                font.setBold(True)
                item.setFont(0, font)
                root.setExpanded(True)
                subgroup.setExpanded(True)
            elif rootTitle == "Other scene data":
                item.setForeground(0, qt.QColor(115, 115, 115))
            if entry["kind"] == "segments":
                item.setFlags(
                    item.flags()
                    | qt.Qt.ItemIsAutoTristate
                )
                segmentationNode = (
                    entry.get("segmentationNode")
                    or self._parameterNode.teethSegmentation
                )
                segmentation = (
                    segmentationNode.GetSegmentation()
                    if segmentationNode
                    else None
                )
                for segmentId in entry["segmentIds"]:
                    childEntry = self._workflowSegmentLeafEntry(entry, segmentId)
                    self._workflowViewEntriesByKey[childEntry["key"]] = childEntry
                    segment = segmentation.GetSegment(segmentId) if segmentation else None
                    child = qt.QTreeWidgetItem(item)
                    child.setText(
                        0,
                        segment.GetName() if segment else segmentId,
                    )
                    child.setData(0, qt.Qt.UserRole, childEntry["key"])
                    child.setFlags(child.flags() | qt.Qt.ItemIsUserCheckable)
                    child.setCheckState(
                        0,
                        self._workflowViewEntryCheckState(childEntry),
                    )
        for root in roots.values():
            root.setHidden(root.childCount() == 0)

    def _workflowViewEntryVisibilityRestriction(
        self,
        entry: dict,
        visible: bool,
    ) -> str:
        """Return why an Advanced visibility request is unsafe in Step 6."""

        if not visible or not self._parameterNode or not self.logic:
            return ""
        if int(self.ui.workflowStageComboBox.currentIndex) != 10:
            return ""
        sceneKind = self._step6SceneKind()
        category = entry["category"]
        if sceneKind == "conflict":
            return _(
                "Resolve the Step 6 case/phantom source conflict before changing robot-workspace visibility."
            )
        if sceneKind == "phantom" and (
            entry.get("anatomyScopes")
            or category in {
                "case_volume",
                "case_volume_3d",
                "case_jaw_opening",
                "target_mask",
                "bounds",
                "trajectory",
                "target_docking",
                "final",
            }
        ):
            return _(
                "The disposable phantom source is active; case/CBCT anatomy is intentionally unavailable in this Step 6 view."
            )
        if sceneKind == "case" and category in {
            "phantom",
            "phantom_landmarks",
        }:
            return _(
                "The CBCT workflow case is active; disposable phantom nodes are intentionally unavailable in this Step 6 view."
            )
        rosActive = self.logic.isRos2MotionControlActive(
            self._parameterNode.robotBaseTransform
        )
        if rosActive and category == "robot_mrml":
            return _(
                "ROS robot control is active; the MRML-only robot is hidden to prevent two authoritative robot states."
            )
        if not rosActive and category in {"robot_ros", "robot_goal"}:
            return _(
                "ROS robot control is inactive; ROS current/goal representations cannot be enabled yet."
            )
        return ""

    def _setWorkflowViewEntryVisible(
        self,
        entry: dict,
        visible: bool,
    ) -> str:
        restriction = self._workflowViewEntryVisibilityRestriction(
            entry,
            visible,
        )
        if restriction:
            return restriction
        if entry["kind"] == "node":
            displayNode = entry["node"].GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(visible)
        elif entry["kind"] == "nodes":
            for node in entry["nodes"]:
                displayNode = node.GetDisplayNode() if node else None
                if displayNode:
                    displayNode.SetVisibility(visible)
        elif entry["kind"] == "volume_rendering":
            entry["displayNode"].SetVisibility(visible)
        else:
            segmentationNode = (
                entry.get("segmentationNode")
                or self._parameterNode.teethSegmentation
            )
            displayNode = segmentationNode.GetDisplayNode() if segmentationNode else None
            if displayNode:
                wasModifying = displayNode.StartModify()
                try:
                    for segmentId in entry["segmentIds"]:
                        displayNode.SetSegmentVisibility(segmentId, visible)
                    segmentation = segmentationNode.GetSegmentation()
                    segmentIds = vtk.vtkStringArray()
                    segmentation.GetSegmentIDs(segmentIds)
                    hasVisibleSegment = any(
                        displayNode.GetSegmentVisibility(
                            segmentIds.GetValue(segmentIndex)
                        )
                        for segmentIndex in range(segmentIds.GetNumberOfValues())
                    )
                    displayNode.SetVisibility(hasVisibleSegment)
                    displayNode.SetVisibility2D(hasVisibleSegment)
                    displayNode.SetVisibility3D(hasVisibleSegment)
                finally:
                    displayNode.EndModify(wasModifying)
        return ""

    def onWorkflowViewTreeItemChanged(self, item, column: int) -> None:
        del column
        if self._updatingWorkflowViewUI or not item or not self._parameterNode:
            return
        self._ensureWorkflowViewSnapshot()
        desired = item.checkState(0) == qt.Qt.Checked
        key = str(item.data(0, qt.Qt.UserRole) or "")
        entriesToChange = []
        if key and key in self._workflowViewEntriesByKey:
            entriesToChange.append(self._workflowViewEntriesByKey[key])
        else:
            stack = [item.child(index) for index in range(item.childCount())]
            while stack:
                child = stack.pop()
                childKey = str(child.data(0, qt.Qt.UserRole) or "")
                if childKey and childKey in self._workflowViewEntriesByKey:
                    entriesToChange.append(self._workflowViewEntriesByKey[childKey])
                    continue
                stack.extend(
                    child.child(index) for index in range(child.childCount())
                )
        restrictions = []
        self._updatingWorkflowViewUI = True
        try:
            for entry in entriesToChange:
                restriction = self._setWorkflowViewEntryVisible(entry, desired)
                if restriction and restriction not in restrictions:
                    restrictions.append(restriction)
        finally:
            self._updatingWorkflowViewUI = False
        self._workflowViewVisibleKeys = {
            entryKey
            for entryKey, entry in self._workflowViewEntriesByKey.items()
            if self._workflowViewEntryCheckState(entry) != qt.Qt.Unchecked
        }
        self._workflowViewActivePresetKey = "custom"
        self._workflowViewComposition = None
        self._enforceStep6OpenedJawDisplaySeparation()
        if restrictions:
            self.ui.workflowViewStatusLabel.text = " ".join(restrictions)
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b06a00;"
        else:
            self.ui.workflowViewStatusLabel.text = _(
                "Custom object visibility; geometry, mask contents, and workflow lineage are unchanged."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #1f5f99;"
        self._updateWorkflowViewControls()
        self._updateTemplateGuideVisibilityControls()

    def _updateWorkflowViewControls(self) -> None:
        if not hasattr(self, "ui"):
            return
        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        active = bool(self._parameterNode and self.logic)
        if self._workflowViewStageLabel:
            stageTitle = str(self.ui.workflowStageComboBox.currentText or "")
            self._workflowViewStageLabel.text = _(
                "Active step: %1\nRecommended: %2."
            ).replace("%1", stageTitle or str(stageIndex + 1)).replace(
                "%2", recommended_view_description(stageIndex)
            )
        self.ui.workflowViewGroupBox.visible = False
        self._setWorkflowViewAvailability(active)
        if not active:
            self._workflowViewEntriesByKey = {}
            self._updatingWorkflowViewUI = True
            try:
                self.ui.workflowViewPresetComboBox.clear()
                self.ui.workflowViewPresetComboBox.addItem(
                    _("View presets unavailable"),
                    "",
                )
                self.ui.workflowViewElementsListWidget.clear()
                if self._workflowAdvancedTree:
                    self._workflowAdvancedTree.clear()
                self.ui.workflowViewStatusLabel.text = _(
                    "Element visibility controls need an active DENTOBOT case."
                )
                self.ui.workflowViewStatusLabel.styleSheet = "color: #6b6b6b;"
            finally:
                self._updatingWorkflowViewUI = False
            return
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {
            entry["key"]: entry for entry in entries
        }
        if self._step6ViewContextWidget:
            isStep6 = stageIndex == len(self._workflowStageEntries()) - 1
            self._step6ViewContextWidget.visible = isStep6
            if isStep6 and self._step6ViewContextLabel:
                sceneKind = self._step6SceneKind()
                rosActive = self.logic.isRos2MotionControlActive(
                    self._parameterNode.robotBaseTransform
                )
                robotSource = (
                    _("ROS robot")
                    if rosActive
                    else _("MRML robot")
                    if self.logic.robotModelNodes()
                    else _("not loaded")
                )
                if sceneKind == "case":
                    openingIssues = self.logic.step6CaseJawOpeningFreshnessIssues(
                        self._parameterNode
                    )
                    preparation = (
                        _("opened-jaw planning anatomy is current")
                        if not openingIssues
                        else _("TMJ opening must be completed")
                    )
                elif sceneKind == "phantom":
                    preparation = _("draft phantom test scene")
                elif sceneKind == "conflict":
                    preparation = _("CONFLICT — resolve case versus phantom")
                else:
                    preparation = _("load one case package or the draft phantom")
                baseState = (
                    _("base locked")
                    if self._parameterNode.robotBaseMountLocked
                    else _("base placement unlocked")
                )
                self._step6ViewContextLabel.text = _(
                    "Scene: %1 · Robot: %2 · %3 · %4.\n"
                    "Case/phantom and MRML/ROS sources are mutually exclusive in "
                    "the recommended view. Earlier planning markups are read-only here."
                ).replace("%1", sceneKind).replace("%2", robotSource).replace(
                    "%3", preparation
                ).replace("%4", baseState)
        teethCounts = {"upper": 0, "lower": 0}
        for entry in entries:
            if entry["kind"] != "segments":
                continue
            if entry["category"] == "upper_teeth":
                teethCounts["upper"] += len(entry["segmentIds"])
            elif entry["category"] == "lower_teeth":
                teethCounts["lower"] += len(entry["segmentIds"])
        for (jaw, dimension), button in self._workflowJawViewButtons.items():
            count = (
                teethCounts["upper"] + teethCounts["lower"]
                if jaw == "all"
                else teethCounts[jaw]
            )
            button.enabled = active and count > 0
            button.setProperty("dentobotAvailable", count > 0)
            button.toolTip = _(
                "%1 recognized permanent-tooth mask(s). Show them in %2."
            ).replace("%1", str(count)).replace(
                "%2",
                {"2d": _("2D slices"), "3d": _("3D"), "both": _("2D and 3D")}[dimension],
            )
        if self._workflowRecommendedViewButton:
            self._workflowRecommendedViewButton.enabled = active and bool(entries)
        if not self._workflowViewPriorState and not self._workflowViewActivePresetKey:
            teethCount = teethCounts["upper"] + teethCounts["lower"]
            if teethCount:
                self.ui.workflowViewStatusLabel.text = _(
                    "%1 permanent-tooth mask(s) recognized from FDI labels."
                ).replace("%1", str(teethCount))
                self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"
            elif entries:
                self.ui.workflowViewStatusLabel.text = _(
                    "No FDI-labelled permanent-tooth masks are available; "
                    "step-relevant volumes and objects can still be selected."
                )
                self.ui.workflowViewStatusLabel.styleSheet = "color: #b36b00;"
            else:
                self.ui.workflowViewStatusLabel.text = _(
                    "No case volume, segmentation masks, or workflow objects "
                    "are available in the current scene yet."
                )
                self.ui.workflowViewStatusLabel.styleSheet = "color: #6b6b6b;"
        self._updatingWorkflowViewUI = True
        try:
            comboBox = self.ui.workflowViewPresetComboBox
            definitions = self._workflowViewPresetDefinitions(stageIndex, entries)
            comboBox.clear()
            selectedIndex = 0
            for index, (key, label) in enumerate(definitions):
                comboBox.addItem(label, key)
                if key == self._workflowViewActivePresetKey:
                    selectedIndex = index
            comboBox.currentIndex = selectedIndex

            self._updateWorkflowViewCompositionControls(stageIndex)
            self._populateWorkflowAdvancedTree(entries, stageIndex)
            self.ui.restoreWorkflowViewButton.enabled = bool(
                self._workflowViewPriorState
            )
            self.ui.frameWorkflowViewButton.enabled = bool(entries)
        finally:
            self._updatingWorkflowViewUI = False

    def _setWorkflowViewAvailability(self, active: bool) -> None:
        """Keep both display tabs available throughout the workflow."""

        active = bool(active)
        self.ui.workflowViewPresetComboBox.enabled = active
        if self._workflowRecommendedViewButton:
            self._workflowRecommendedViewButton.enabled = active
        for widget in (
            self._workflowAnatomyComboBox,
            self._workflowDimensionComboBox,
            self._workflowCbctComboBox,
            self._workflowOverlayButton,
            self._workflowAdvancedTree,
        ):
            if widget:
                widget.enabled = active
        for button in self._workflowJawViewButtons.values():
            if not active:
                button.enabled = False
        self.ui.frameWorkflowViewButton.enabled = (
            active and bool(self._workflowViewEntriesByKey)
        )
        self.ui.restoreWorkflowViewButton.enabled = (
            active and bool(self._workflowViewPriorState)
        )
        if self._viewControlsTabWidget:
            self._viewControlsTabWidget.setTabEnabled(
                self._viewControlsElementsTabIndex,
                active,
            )
            self._viewControlsTabWidget.setTabEnabled(
                self._viewControlsDisplayTabIndex,
                True,
            )

    def _ensureWorkflowViewSnapshot(self) -> None:
        if self._workflowViewPriorState or not self.logic:
            return
        self._restoreAssistedTrajectoryFocus(updateUi=False)
        self._restoreTemplateSupportBoundaryFocus(updateUi=False)
        self._workflowViewPriorState = self.logic.captureWorkflowDisplayState(
            self._parameterNode.teethSegmentation if self._parameterNode else None,
            self._workflowManagedDisplayNodes(),
        )
        segmentationStates = {}
        primary = self._parameterNode.teethSegmentation if self._parameterNode else None
        for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
            if segmentationNode is primary:
                continue
            segmentationStates[segmentationNode.GetID()] = (
                self.logic.captureWorkflowDisplayState(segmentationNode, [])
            )
        self._workflowViewPriorState["additionalSegmentations"] = segmentationStates
        self._workflowViewPriorState["volumeRendering"] = {
            entry["displayNode"].GetID(): bool(entry["displayNode"].GetVisibility())
            for entry in self._workflowViewEntriesByKey.values()
            if entry["kind"] == "volume_rendering"
            and entry["displayNode"].GetID()
        }
        self._workflowViewPriorState["sliceComposites"] = {
            composite.GetID(): {
                "background": composite.GetBackgroundVolumeID(),
                "foreground": composite.GetForegroundVolumeID(),
                "label": composite.GetLabelVolumeID(),
                "foregroundOpacity": float(composite.GetForegroundOpacity()),
                "labelOpacity": float(composite.GetLabelOpacity()),
            }
            for composite in slicer.util.getNodesByClass(
                "vtkMRMLSliceCompositeNode"
            )
            if composite.GetID()
        }
        self._workflowViewCreatedRendererNodeIds.clear()
        self._workflowViewCreatedPropertyNodeIds.clear()

    def _extendWorkflowViewSnapshotForNewNodes(self, nodes: list) -> None:
        if not self._workflowViewPriorState or not self.logic:
            return
        captured = self.logic.captureWorkflowDisplayState(None, nodes)
        storedNodes = self._workflowViewPriorState.setdefault("nodes", {})
        for nodeId, state in captured.get("nodes", {}).items():
            storedNodes.setdefault(nodeId, state)

    def _applyWorkflowViewKeys(
        self,
        visibleKeys: set[str],
        *,
        activePresetKey: str,
        updateStatus: bool = True,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        self._ensureWorkflowViewSnapshot()
        entries = list(self._workflowViewEntriesByKey.values())
        managedNodes = self._workflowManagedDisplayNodes()
        self._extendWorkflowViewSnapshotForNewNodes(managedNodes)
        visibleSegmentIds = {
            segmentId
            for entry in entries
            if entry["key"] in visibleKeys and entry["kind"] == "segments"
            and (
                entry.get("segmentationNode") is None
                or entry.get("segmentationNode") is self._parameterNode.teethSegmentation
            )
            for segmentId in entry["segmentIds"]
        }
        visibleNodeIds = set()
        for entry in entries:
            if entry["kind"] == "volume_rendering":
                entry["displayNode"].SetVisibility(entry["key"] in visibleKeys)
                continue
            if entry["key"] not in visibleKeys:
                continue
            if entry["kind"] == "node":
                visibleNodeIds.add(entry["node"].GetID())
            elif entry["kind"] == "nodes":
                for node in entry["nodes"]:
                    if node and node.GetID():
                        visibleNodeIds.add(node.GetID())
        self.logic.applyWorkflowDisplaySelection(
            self._parameterNode.teethSegmentation,
            visibleSegmentIds,
            managedNodes,
            visibleNodeIds,
        )
        self._enforceStep6OpenedJawDisplaySeparation()
        primarySegmentation = self._parameterNode.teethSegmentation
        segmentIdsByNode = {}
        for entry in entries:
            if entry["key"] not in visibleKeys or entry["kind"] != "segments":
                continue
            segmentationNode = entry.get("segmentationNode") or primarySegmentation
            if segmentationNode:
                segmentIdsByNode.setdefault(segmentationNode, set()).update(
                    entry["segmentIds"]
                )
        for segmentationNode in slicer.util.getNodesByClass("vtkMRMLSegmentationNode"):
            if segmentationNode is primarySegmentation:
                continue
            self.logic.applyWorkflowDisplaySelection(
                segmentationNode,
                segmentIdsByNode.get(segmentationNode, set()),
                [],
                set(),
            )
        self._workflowViewVisibleKeys = set(visibleKeys)
        self._workflowViewActivePresetKey = activePresetKey
        if activePresetKey == "trajectory_only":
            self._presentSelectedTrajectory(
                self._parameterNode.trajectoryLine,
                centerSlices=True,
            )
        self.ui.restorePlanningViewButton.enabled = bool(
            self._workflowViewPriorState
        )
        self._updateWorkflowViewControls()
        self._updateTemplateGuideVisibilityControls()
        if updateStatus:
            self.ui.workflowViewStatusLabel.text = _(
                "Applied %1 grouped display selection(s). This changes "
                "visibility only; masks and geometry are unchanged."
            ).replace(
                "%1", str(len(visibleKeys))
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    def _applyWorkflowViewPreset(
        self,
        presetKey: str,
        *,
        updateStatus: bool = True,
    ) -> None:
        if presetKey == "recommended":
            stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
            self._applyWorkflowViewComposition(
                self._recommendedWorkflowViewComposition(stageIndex),
                recommended=True,
                allowRendererCreation=False,
                updateStatus=updateStatus,
            )
            return
        if presetKey == "composition" and self._workflowViewComposition:
            self._applyWorkflowViewComposition(
                self._workflowViewComposition,
                recommended=False,
                allowRendererCreation=True,
                updateStatus=updateStatus,
            )
            return
        self._workflowViewComposition = None
        teethPreset = re.fullmatch(
            r"teeth_(upper|lower|all)_(2d|3d|both)",
            str(presetKey),
        )
        if teethPreset:
            self._applyJawTeethView(
                teethPreset.group(1),
                teethPreset.group(2),
                updateStatus=updateStatus,
            )
            return
        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {
            entry["key"]: entry for entry in entries
        }
        visibleKeys = self._workflowViewKeysForPreset(
            presetKey,
            entries,
            stageIndex,
        )
        self._applyWorkflowViewKeys(
            visibleKeys,
            activePresetKey=presetKey,
            updateStatus=updateStatus,
        )

    def onApplyRecommendedWorkflowView(self, checked: bool = False) -> None:
        """Apply the explicit recommendation for the active workflow step."""

        del checked
        self._applyWorkflowViewPreset("recommended")

    def _applyJawTeethView(
        self,
        jaw: str,
        dimension: str,
        *,
        updateStatus: bool = True,
    ) -> None:
        """Isolate upper/lower tooth masks and independently select 2D/3D."""

        jaw = str(jaw).lower()
        dimension = str(dimension).lower()
        if jaw not in {"upper", "lower", "all"}:
            raise ValueError(_("Jaw view must be upper, lower, or all."))
        if dimension not in {"2d", "3d", "both"}:
            raise ValueError(_("Jaw view dimension must be 2D, 3D, or both."))
        if not self._parameterNode or not self.logic:
            return

        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {
            entry["key"]: entry for entry in entries
        }
        wantedCategories = (
            {"upper_teeth", "lower_teeth"}
            if jaw == "all"
            else {f"{jaw}_teeth"}
        )
        visibleKeys = {
            entry["key"]
            for entry in entries
            if entry["category"] in wantedCategories
        }
        segmentSelections = [
            entry
            for entry in entries
            if entry["key"] in visibleKeys and entry["kind"] == "segments"
        ]
        if not segmentSelections:
            self.ui.workflowViewStatusLabel.text = _(
                "No %1 permanent-tooth masks with valid FDI labels are available."
            ).replace("%1", jaw)
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b36b00;"
            return

        activePresetKey = f"teeth_{jaw}_{dimension}"
        self._applyWorkflowViewKeys(
            visibleKeys,
            activePresetKey=activePresetKey,
            updateStatus=False,
        )
        selectedByNode = {}
        for entry in segmentSelections:
            segmentationNode = (
                entry.get("segmentationNode")
                or self._parameterNode.teethSegmentation
            )
            if segmentationNode:
                selectedByNode.setdefault(segmentationNode, set()).update(
                    entry["segmentIds"]
                )
        for segmentationNode, segmentIds in selectedByNode.items():
            displayNode = segmentationNode.GetDisplayNode()
            if not displayNode or not segmentIds:
                continue
            wasModifying = displayNode.StartModify()
            try:
                displayNode.SetVisibility(True)
                displayNode.SetVisibility2D(dimension in {"2d", "both"})
                displayNode.SetVisibility3D(dimension in {"3d", "both"})
            finally:
                displayNode.EndModify(wasModifying)
        self._enforceStep6OpenedJawDisplaySeparation()

        self._workflowViewActivePresetKey = activePresetKey
        self._workflowViewVisibleKeys = set(visibleKeys)
        self._updateWorkflowViewControls()
        if updateStatus:
            self.onFrameWorkflowView()
            jawLabel = {
                "upper": _("Upper-jaw"),
                "lower": _("Lower-jaw"),
                "all": _("All"),
            }[jaw]
            dimensionLabel = {
                "2d": _("2D slices only"),
                "3d": _("3D view only"),
                "both": _("2D slices and 3D view"),
            }[dimension]
            maskCount = sum(
                len(segmentIds) for segmentIds in selectedByNode.values()
            )
            self.ui.workflowViewStatusLabel.text = _(
                "%1 tooth masks: %2 mask(s), shown in %3. Other workflow "
                "objects are hidden; mask geometry is unchanged."
            ).replace("%1", jawLabel).replace("%2", str(maskCount)).replace(
                "%3", dimensionLabel
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    @staticmethod
    def _comboBoxData(comboBox) -> str:
        if not comboBox or int(comboBox.currentIndex) < 0:
            return ""
        return str(comboBox.itemData(int(comboBox.currentIndex)) or "")

    @staticmethod
    def _setComboBoxData(comboBox, value: str) -> None:
        if not comboBox:
            return
        for index in range(int(comboBox.count)):
            if str(comboBox.itemData(index) or "") == str(value):
                comboBox.currentIndex = index
                return

    def _recommendedWorkflowViewComposition(
        self,
        stageIndex: int,
    ) -> ViewComposition:
        composition = recommended_view_composition(stageIndex)
        if not self._parameterNode or not self.logic:
            return composition
        if stageIndex == 6:
            record = self._targetToothRecordsById.get(
                self._parameterNode.targetToothSegmentId,
                {},
            )
            jaw = dental_jaw_from_fdi(record.get("fdiNumber"))
            if jaw:
                composition = composition.updated(
                    anatomy_scope=f"{jaw}_jaw_anatomy"
                )
        elif stageIndex == 9 and not self._parameterNode.finalPrintableTemplateModel:
            composition = composition.updated(
                overlay_groups=frozenset({"docks", "shell_components"})
            )
        elif stageIndex == 10:
            sceneKind = self._step6SceneKind()
            if sceneKind == "phantom":
                composition = ViewComposition(
                    anatomy_scope="none",
                    anatomy_dimension="3d",
                    cbct_mode="off",
                    overlay_groups=frozenset({"phantom", "robot"}),
                    anatomy_opacity=0.35,
                )
            elif sceneKind == "none":
                composition = ViewComposition()
        return composition

    def _workflowViewCompositionFromControls(self) -> ViewComposition:
        overlays = frozenset(
            key
            for key, action in self._workflowOverlayActions.items()
            if bool(action.checked)
        )
        previousOpacity = (
            self._workflowViewComposition.anatomy_opacity
            if self._workflowViewComposition
            else self._recommendedWorkflowViewComposition(
                int(self.ui.workflowStageComboBox.currentIndex)
            ).anatomy_opacity
        )
        return ViewComposition(
            anatomy_scope=self._comboBoxData(self._workflowAnatomyComboBox)
            or "none",
            anatomy_dimension=self._comboBoxData(
                self._workflowDimensionComboBox
            )
            or "both",
            cbct_mode=self._comboBoxData(self._workflowCbctComboBox) or "off",
            overlay_groups=overlays,
            anatomy_opacity=previousOpacity,
        )

    def _updateWorkflowViewCompositionControls(self, stageIndex: int) -> None:
        if not self._workflowAnatomyComboBox:
            return
        composition = self._workflowViewComposition
        if composition is None:
            composition = self._recommendedWorkflowViewComposition(stageIndex)
        self._setComboBoxData(
            self._workflowAnatomyComboBox,
            composition.anatomy_scope,
        )
        self._setComboBoxData(
            self._workflowDimensionComboBox,
            composition.anatomy_dimension,
        )
        self._setComboBoxData(self._workflowCbctComboBox, composition.cbct_mode)
        for key, action in self._workflowOverlayActions.items():
            action.checked = key in composition.overlay_groups
        overlayCount = len(composition.overlay_groups)
        self._workflowOverlayButton.text = (
            _("No overlays")
            if overlayCount == 0
            else _("%1 overlay group(s)").replace("%1", str(overlayCount))
        )
        if self._workflowAutoRecommendCheckBox:
            self._workflowAutoRecommendCheckBox.checked = bool(
                self.ui.autoWorkflowViewCheckBox.checked
            )

    def _onWorkflowAutoRecommendToggled(self, checked: bool) -> None:
        if self._updatingWorkflowViewUI:
            return
        self.ui.autoWorkflowViewCheckBox.checked = bool(checked)

    def onWorkflowViewCompositionChanged(self, index: int = -1) -> None:
        del index
        if self._updatingWorkflowViewUI or not self._parameterNode:
            return
        composition = self._workflowViewCompositionFromControls()
        self._applyWorkflowViewComposition(
            composition,
            recommended=False,
            allowRendererCreation=True,
        )

    def _onWorkflowOverlayToggled(self, overlayKey: str, checked: bool) -> None:
        del overlayKey, checked
        if self._updatingWorkflowViewUI or not self._parameterNode:
            return
        composition = self._workflowViewCompositionFromControls()
        self._applyWorkflowViewComposition(
            composition,
            recommended=False,
            allowRendererCreation=True,
        )

    def _workflowViewKeysForComposition(
        self,
        composition: ViewComposition,
        entries: list[dict],
        stageIndex: int,
    ) -> set[str]:
        overlayCategories = set().union(
            *(
                OVERLAY_CATEGORY_MAP[key]
                for key in composition.overlay_groups
            ),
        ) if composition.overlay_groups else set()
        visibleKeys: set[str] = set()
        for entry in entries:
            category = entry["category"]
            anatomyVisible = False
            if composition.anatomy_scope == "target_tooth":
                anatomyVisible = category == "target_mask"
            elif composition.anatomy_scope == "target_support":
                anatomyVisible = category in {"target_mask", "support_mask"}
            elif composition.anatomy_scope != "none":
                anatomyVisible = composition.anatomy_scope in entry.get(
                    "anatomyScopes",
                    (),
                )
            cbctVisible = (
                category == "case_volume"
                and composition.cbct_mode in {"slices", "both"}
            ) or (
                category == "case_volume_3d"
                and composition.cbct_mode in {"intensity_3d", "both"}
            )
            if anatomyVisible or cbctVisible or category in overlayCategories:
                visibleKeys.add(entry["key"])

        if stageIndex == 4 and "trajectories" in composition.overlay_groups:
            selected = self._parameterNode.trajectoryLine
            visibleKeys = {
                key
                for key in visibleKeys
                if not key.startswith("trajectory:")
                or (
                    selected is not None
                    and key == f"trajectory:{selected.GetID()}"
                )
            }
        if stageIndex == 10:
            sceneKind = self._step6SceneKind()
            rosActive = self.logic.isRos2MotionControlActive(
                self._parameterNode.robotBaseTransform
            )
            for entry in entries:
                category = entry["category"]
                if sceneKind == "phantom" and (
                    entry.get("anatomyScopes")
                    or category in {
                        "case_volume",
                        "case_volume_3d",
                        "case_jaw_opening",
                        "target_mask",
                        "bounds",
                        "trajectory",
                        "target_docking",
                        "final",
                    }
                ):
                    visibleKeys.discard(entry["key"])
                if sceneKind == "case" and category in {
                    "phantom",
                    "phantom_landmarks",
                }:
                    visibleKeys.discard(entry["key"])
                if rosActive and category == "robot_mrml":
                    visibleKeys.discard(entry["key"])
                if not rosActive and category in {"robot_ros", "robot_goal"}:
                    visibleKeys.discard(entry["key"])
        return visibleKeys

    def _setWorkflowCbctSlices(self, enabled: bool) -> None:
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        volumeId = volume.GetID() if volume else None
        for composite in slicer.util.getNodesByClass(
            "vtkMRMLSliceCompositeNode"
        ):
            if enabled and volumeId:
                composite.SetBackgroundVolumeID(volumeId)
            elif volumeId and composite.GetBackgroundVolumeID() == volumeId:
                composite.SetBackgroundVolumeID(None)

    def _ensureExplicitWorkflowCbctRenderer(self):
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        if not volume or not hasattr(slicer.modules, "volumerendering"):
            return None
        logic = slicer.modules.volumerendering.logic()
        display = logic.GetFirstVolumeRenderingDisplayNode(volume)
        if display:
            return display
        priorDisplayIds = {
            node.GetID()
            for node in slicer.util.getNodesByClass(
                "vtkMRMLVolumeRenderingDisplayNode"
            )
        }
        priorPropertyIds = {
            node.GetID()
            for node in slicer.util.getNodesByClass("vtkMRMLVolumePropertyNode")
        }
        display = logic.CreateDefaultVolumeRenderingNodes(volume)
        if display and display.GetID() not in priorDisplayIds:
            self._workflowViewCreatedRendererNodeIds.add(display.GetID())
        self._workflowViewCreatedPropertyNodeIds.update(
            node.GetID()
            for node in slicer.util.getNodesByClass("vtkMRMLVolumePropertyNode")
            if node.GetID() not in priorPropertyIds
        )
        return display

    def _applyWorkflowCbctMode(
        self,
        composition: ViewComposition,
        *,
        allowRendererCreation: bool,
    ) -> None:
        self._setWorkflowCbctSlices(composition.cbct_mode in {"slices", "both"})
        wantsRenderer = composition.cbct_mode in {"intensity_3d", "both"}
        display = None
        volume = self._parameterNode.inputVolume if self._parameterNode else None
        if volume and hasattr(slicer.modules, "volumerendering"):
            display = slicer.modules.volumerendering.logic().GetFirstVolumeRenderingDisplayNode(
                volume
            )
        if wantsRenderer and display is None and allowRendererCreation:
            display = self._ensureExplicitWorkflowCbctRenderer()
        if display:
            display.SetVisibility(bool(wantsRenderer))

    def _applyWorkflowAnatomyAppearance(
        self,
        composition: ViewComposition,
        visibleKeys: set[str],
    ) -> None:
        selectedByNode: dict[object, set[str]] = {}
        for entry in self._workflowViewEntriesByKey.values():
            if entry["key"] not in visibleKeys or entry["kind"] != "segments":
                continue
            segmentationNode = (
                entry.get("segmentationNode")
                or self._parameterNode.teethSegmentation
            )
            if segmentationNode:
                selectedByNode.setdefault(segmentationNode, set()).update(
                    entry["segmentIds"]
                )
        show2d = composition.anatomy_dimension in {"2d", "both"}
        show3d = composition.anatomy_dimension in {"3d", "both"}
        for segmentationNode, segmentIds in selectedByNode.items():
            display = segmentationNode.GetDisplayNode()
            if not display:
                continue
            wasModifying = display.StartModify()
            try:
                display.SetVisibility(bool(segmentIds))
                display.SetVisibility2D(show2d and bool(segmentIds))
                display.SetVisibility3D(show3d and bool(segmentIds))
                for segmentId in segmentIds:
                    display.SetSegmentVisibility3D(segmentId, show3d)
                    if hasattr(display, "SetSegmentVisibility2DFill"):
                        display.SetSegmentVisibility2DFill(segmentId, show2d)
                    if hasattr(display, "SetSegmentVisibility2DOutline"):
                        display.SetSegmentVisibility2DOutline(segmentId, show2d)
                    display.SetSegmentOpacity3D(
                        segmentId,
                        composition.anatomy_opacity,
                    )
            finally:
                display.EndModify(wasModifying)
        for entry in self._workflowViewEntriesByKey.values():
            if entry["key"] not in visibleKeys or entry["kind"] not in {"node", "nodes"}:
                continue
            if entry["category"] == "robot_goal":
                opacity = 0.3
            else:
                opacity = 1.0
            nodes = [entry["node"]] if entry["kind"] == "node" else entry["nodes"]
            for node in nodes:
                display = node.GetDisplayNode() if node else None
                if display and hasattr(display, "SetOpacity"):
                    display.SetOpacity(opacity)

    def _applyWorkflowViewComposition(
        self,
        composition: ViewComposition,
        *,
        recommended: bool,
        allowRendererCreation: bool,
        updateStatus: bool = True,
    ) -> None:
        if not self._parameterNode or not self.logic:
            return
        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        if stageIndex == 10 and self._step6SceneKind() == "conflict":
            self.ui.workflowViewStatusLabel.text = _(
                "Step 6 has both case and phantom scene sources. Resolve the scene conflict before composing the robot workspace view."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b00020;"
            return
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {entry["key"]: entry for entry in entries}
        self._ensureWorkflowViewSnapshot()
        self._applyWorkflowCbctMode(
            composition,
            allowRendererCreation=allowRendererCreation,
        )
        entries = self._workflowViewEntries(stageIndex)
        self._workflowViewEntriesByKey = {entry["key"]: entry for entry in entries}
        visibleKeys = self._workflowViewKeysForComposition(
            composition,
            entries,
            stageIndex,
        )
        self._workflowViewComposition = composition
        activeKey = "recommended" if recommended else "composition"
        self._applyWorkflowViewKeys(
            visibleKeys,
            activePresetKey=activeKey,
            updateStatus=False,
        )
        self._applyWorkflowAnatomyAppearance(composition, visibleKeys)
        self._enforceStep6OpenedJawDisplaySeparation()
        self._updateWorkflowViewControls()
        if updateStatus:
            self.ui.workflowViewStatusLabel.text = _(
                "Applied one composable display view. Anatomy, slices, renderers, and overlays changed presentation only."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    def _workflowOwnedMarkupStages(self) -> dict[object, int]:
        """Return editable-stage ownership for DENTOBOT markups only."""

        if not self._parameterNode:
            return {}
        stages: dict[object, int] = {}
        fieldStages = {
            "targetToothBoundsRoi": 4,
            "trajectoryLine": 4,
            "assistedTrajectoryEntries": 4,
            "targetDockingReferencePlane": 6,
            "templateSupportBoundaryCurve": 7,
            "templateSupportBoundaryPlane": 7,
            "templateInsertionDirection": 8,
            "templateShellRoi": 8,
            "templateTrimPlane": 9,
            "templateTrimCurve": 9,
            "draftJawLandmarks": 10,
            "draftJawGapLine": 10,
            "step6CaseJawLandmarks": 10,
            "step6CaseJawGapLine": 10,
            "step6OpenedTrajectoryLine": 10,
            "robotMountPlane": 10,
        }
        for fieldName, stage in fieldStages.items():
            node = getattr(self._parameterNode, fieldName, None)
            if node and node.IsA("vtkMRMLMarkupsNode"):
                stages[node] = stage
        roleStages = {
            "TemplateSupportBoundary": 7,
            "TemplateSupportBoundaryPlane": 7,
            "TargetDockingReferencePlane": 6,
            "TargetDockingMeasurement": 6,
            "TemplateShellTrimROI": 8,
            "RobotMountPlane": 10,
            "DraftJawLandmarks": 10,
            "DraftJawGapLine": 10,
            "Step6CaseJawLandmarks": 10,
            "Step6CaseJawGapLine": 10,
        }
        for node in slicer.util.getNodesByClass(
            "vtkMRMLDisplayableNode"
        ):
            if not node.IsA("vtkMRMLMarkupsNode"):
                continue
            if node.GetAttribute("DENTOBOT.TrajectoryRole"):
                stages[node] = 4
                continue
            if node.GetAttribute("DENTOBOT.BoundsRole"):
                stages[node] = 4
                continue
            role = node.GetAttribute("DENTOBOT.MarkupsRole") or ""
            if role in roleStages:
                stages[node] = roleStages[role]
        return stages

    def _step6OwnedMarkupMayInteract(self, node) -> bool:
        if not self._parameterNode or not self.logic:
            return False
        role = node.GetAttribute("DENTOBOT.MarkupsRole") or ""
        sceneKind = self._step6SceneKind()
        if role == self.logic.STEP6_CASE_JAW_LANDMARKS_ROLE:
            return bool(
                sceneKind == "case"
                and self.logic.step6CaseJawOpeningFreshnessIssues(
                    self._parameterNode
                )
            )
        if role == self.logic.DRAFT_JAW_LANDMARKS_ROLE:
            return bool(
                sceneKind == "phantom"
                and not self._parameterNode.draftJawTransform
            )
        if role == self.logic.ROBOT_MOUNT_PLANE_ROLE:
            return bool(
                self._step6RobotPresent()
                and not self._parameterNode.robotBaseMountLocked
                and not self.logic.isRos2MotionControlActive(
                    self._parameterNode.robotBaseTransform
                )
            )
        return False

    def _restoreStageExclusiveInteractionLocks(self) -> None:
        for nodeId, state in list(
            self._stageExclusiveInteractionPriorState.items()
        ):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node:
                node.SetLocked(bool(state["locked"]))
                node.SetSelectable(bool(state["selectable"]))
        self._stageExclusiveInteractionPriorState.clear()

    def _updateStageExclusiveInteractionLocks(self, stageIndex: int) -> None:
        """Make non-owning workflow markups non-selectable and non-draggable."""

        ownedStages = self._workflowOwnedMarkupStages()
        restrictedIds = set()
        for node, ownerStage in ownedStages.items():
            allowInteraction = ownerStage == int(stageIndex)
            if allowInteraction and ownerStage == 10:
                allowInteraction = self._step6OwnedMarkupMayInteract(node)
            nodeId = node.GetID()
            if not nodeId:
                continue
            if allowInteraction:
                prior = self._stageExclusiveInteractionPriorState.pop(
                    nodeId,
                    None,
                )
                if prior:
                    node.SetLocked(bool(prior["locked"]))
                    node.SetSelectable(bool(prior["selectable"]))
                continue
            restrictedIds.add(nodeId)
            self._stageExclusiveInteractionPriorState.setdefault(
                nodeId,
                {
                    "locked": bool(node.GetLocked()),
                    "selectable": bool(node.GetSelectable()),
                },
            )
            node.SetLocked(True)
            node.SetSelectable(False)
        for nodeId in list(self._stageExclusiveInteractionPriorState):
            if nodeId in restrictedIds:
                continue
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            prior = self._stageExclusiveInteractionPriorState.pop(nodeId)
            if node:
                node.SetLocked(bool(prior["locked"]))
                node.SetSelectable(bool(prior["selectable"]))

    def _activateWorkflowViewStage(
        self,
        stageIndex: int,
        *,
        stageChanged: bool,
    ) -> None:
        active = bool(self._parameterNode and self.logic)
        self._workflowViewStageIndex = stageIndex
        if stageIndex == 4:
            try:
                self._enableCrossViewNavigation()
            except RuntimeError as exc:
                self.ui.crossViewNavigationStatusLabel.text = str(exc)
                self.ui.crossViewNavigationStatusLabel.styleSheet = (
                    "color: #b00020;"
                )
        else:
            self._restoreCrossViewNavigation(updateUi=False)
        self._updateWorkflowViewControls()
        if stageChanged:
            if self.ui.autoWorkflowViewCheckBox.checked:
                self._applyWorkflowViewPreset("recommended")
            else:
                self._workflowViewActivePresetKey = "custom"
                self._workflowViewVisibleKeys = {
                    entry["key"]
                    for entry in self._workflowViewEntriesByKey.values()
                    if self._workflowViewEntryCheckState(entry)
                    != qt.Qt.Unchecked
                }
                self.ui.workflowViewStatusLabel.text = _(
                    "Current scene visibility is unchanged; choose a quick "
                    "view or toggle individual elements."
                )
                self.ui.workflowViewStatusLabel.styleSheet = "color: #1f5f99;"
                self._updateWorkflowViewControls()

    def _refreshWorkflowViewAfterStateChange(self) -> None:
        """Keep an active display preset authoritative as MRML inputs change."""

        stageIndex = int(self.ui.workflowStageComboBox.currentIndex)
        self._updateWorkflowViewControls()
        if not self._workflowViewPriorState:
            return
        if self._workflowViewActivePresetKey == "custom":
            availableKeys = set(self._workflowViewEntriesByKey)
            visibleKeys = self._workflowViewVisibleKeys & availableKeys
            self._applyWorkflowViewKeys(
                visibleKeys,
                activePresetKey="custom",
                updateStatus=False,
            )
        elif self._workflowViewActivePresetKey:
            self._applyWorkflowViewPreset(
                self._workflowViewActivePresetKey,
                updateStatus=False,
            )

    def onWorkflowViewPresetChanged(self, index: int) -> None:
        if self._updatingWorkflowViewUI or index < 0:
            return
        presetKey = str(self.ui.workflowViewPresetComboBox.itemData(index) or "")
        if not presetKey or presetKey in {"scene", "custom"}:
            return
        self._applyWorkflowViewPreset(presetKey)

    def onWorkflowViewElementChanged(self, item) -> None:
        if self._updatingWorkflowViewUI or not item or not self._parameterNode:
            return
        key = str(item.data(qt.Qt.UserRole) or "")
        entry = self._workflowViewEntriesByKey.get(key)
        if not entry:
            return
        self._ensureWorkflowViewSnapshot()
        visible = item.checkState() == qt.Qt.Checked
        if entry["kind"] == "node":
            displayNode = entry["node"].GetDisplayNode()
            if displayNode:
                displayNode.SetVisibility(visible)
        elif entry["kind"] == "nodes":
            for node in entry["nodes"]:
                displayNode = node.GetDisplayNode() if node else None
                if displayNode:
                    displayNode.SetVisibility(visible)
        elif entry["kind"] == "volume_rendering":
            entry["displayNode"].SetVisibility(visible)
        else:
            segmentationNode = entry.get("segmentationNode") or self._parameterNode.teethSegmentation
            displayNode = segmentationNode.GetDisplayNode() if segmentationNode else None
            if displayNode:
                wasModifying = displayNode.StartModify()
                try:
                    for segmentId in entry["segmentIds"]:
                        displayNode.SetSegmentVisibility(segmentId, visible)
                    segmentation = segmentationNode.GetSegmentation()
                    segmentIds = vtk.vtkStringArray()
                    segmentation.GetSegmentIDs(segmentIds)
                    hasVisibleSegment = any(
                        displayNode.GetSegmentVisibility(
                            segmentIds.GetValue(segmentIndex)
                        )
                        for segmentIndex in range(segmentIds.GetNumberOfValues())
                    )
                    displayNode.SetVisibility(hasVisibleSegment)
                    displayNode.SetVisibility2D(hasVisibleSegment)
                    displayNode.SetVisibility3D(hasVisibleSegment)
                finally:
                    displayNode.EndModify(wasModifying)
        if visible:
            self._workflowViewVisibleKeys.add(key)
        else:
            self._workflowViewVisibleKeys.discard(key)
        self._workflowViewActivePresetKey = "custom"
        self._workflowViewComposition = None
        self.ui.workflowViewStatusLabel.text = _(
            "Custom display selection; geometry and masks are unchanged."
        )
        self.ui.workflowViewStatusLabel.styleSheet = "color: #1f5f99;"
        self._enforceStep6OpenedJawDisplaySeparation()
        self._updateWorkflowViewControls()
        self._updateTemplateGuideVisibilityControls()

    def _removeWorkflowCreatedVolumeRenderingNodes(self) -> None:
        for nodeId in list(self._workflowViewCreatedRendererNodeIds):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if node:
                slicer.mrmlScene.RemoveNode(node)
        for nodeId in list(self._workflowViewCreatedPropertyNodeIds):
            node = slicer.mrmlScene.GetNodeByID(nodeId)
            if not node:
                continue
            references = vtk.vtkCollection()
            try:
                slicer.mrmlScene.GetReferencingNodes(node, references)
            except Exception:
                continue
            if references.GetNumberOfItems() == 0:
                slicer.mrmlScene.RemoveNode(node)
        self._workflowViewCreatedRendererNodeIds.clear()
        self._workflowViewCreatedPropertyNodeIds.clear()

    def _restoreWorkflowViewState(self, updateUi: bool = True) -> None:
        state = self._workflowViewPriorState
        self._workflowViewPriorState = None
        self._workflowViewActivePresetKey = ""
        self._workflowViewVisibleKeys.clear()
        self._workflowViewComposition = None
        if state and self.logic:
            self._removeWorkflowCreatedVolumeRenderingNodes()
            for compositeId, compositeState in state.get(
                "sliceComposites",
                {},
            ).items():
                composite = slicer.mrmlScene.GetNodeByID(compositeId)
                if not composite:
                    continue
                composite.SetBackgroundVolumeID(compositeState.get("background"))
                composite.SetForegroundVolumeID(compositeState.get("foreground"))
                composite.SetLabelVolumeID(compositeState.get("label"))
                composite.SetForegroundOpacity(
                    float(compositeState.get("foregroundOpacity", 0.0))
                )
                composite.SetLabelOpacity(
                    float(compositeState.get("labelOpacity", 1.0))
                )
            for displayNodeId, visible in state.get("volumeRendering", {}).items():
                displayNode = slicer.mrmlScene.GetNodeByID(displayNodeId)
                if displayNode:
                    displayNode.SetVisibility(bool(visible))
            for segmentationState in state.get(
                "additionalSegmentations", {}
            ).values():
                self.logic.restoreWorkflowDisplayState(segmentationState)
            self.logic.restoreWorkflowDisplayState(state)
            self._enforceStep6OpenedJawDisplaySeparation()
        if updateUi and hasattr(self, "ui"):
            self.ui.restorePlanningViewButton.enabled = False
            self.ui.workflowViewStatusLabel.text = _(
                "Previous segmentation and workflow-object display restored."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"
            self._updateWorkflowViewControls()
            self._updateTemplateGuideVisibilityControls()

    def _enforceStep6OpenedJawDisplaySeparation(self) -> None:
        """Keep closed-pose lower masks out of 3D while the opened proxy is current."""
        if (
            not self._parameterNode
            or not self.logic
            or self._step6SceneKind() != "case"
            or self.logic.step6CaseJawOpeningFreshnessIssues(self._parameterNode)
        ):
            return
        segmentation = self._parameterNode.teethSegmentation
        display = segmentation.GetDisplayNode() if segmentation else None
        if not display:
            return
        for segmentId in self.logic.step6CaseJawSegmentIds(segmentation)["lower"]:
            display.SetSegmentVisibility3D(segmentId, False)
        model = self._parameterNode.step6OpenedLowerJawModel
        modelDisplay = model.GetDisplayNode() if model else None
        if modelDisplay:
            modelDisplay.SetVisibility3D(True)
        if self.logic.step6TargetJaw(self._parameterNode) == "lower":
            sourceModels = (
                [self._parameterNode.finalPrintableTemplateModel]
                if self._parameterNode.finalPrintableTemplateModel
                else [
                    self._parameterNode.draftTemplateSupportModel,
                    self._parameterNode.targetDockingAssemblyModel,
                ]
            )
            for source in sourceModels:
                sourceDisplay = source.GetDisplayNode() if source else None
                if sourceDisplay:
                    sourceDisplay.SetVisibility(False)
            trajectory = self._parameterNode.trajectoryLine
            trajectoryDisplay = trajectory.GetDisplayNode() if trajectory else None
            if trajectoryDisplay:
                trajectoryDisplay.SetVisibility(False)
            for proxy in (
                self._parameterNode.step6OpenedTargetGeometryModel,
                self._parameterNode.step6OpenedTrajectoryLine,
            ):
                proxyDisplay = proxy.GetDisplayNode() if proxy else None
                if proxyDisplay:
                    proxyDisplay.SetVisibility(True)

    def onRestoreWorkflowView(self, checked: bool = False) -> None:
        del checked
        self._restoreWorkflowViewState(updateUi=True)

    def onFrameWorkflowView(self, checked: bool = False) -> None:
        del checked
        if not self._parameterNode or not self.logic:
            return
        boundsList = []
        for entry in self._workflowViewEntriesByKey.values():
            if self._workflowViewEntryCheckState(entry) == qt.Qt.Unchecked:
                continue
            if entry["kind"] == "node":
                bounds = [0.0] * 6
                entry["node"].GetRASBounds(bounds)
                boundsList.append(bounds)
            elif entry["kind"] == "nodes":
                for node in entry["nodes"]:
                    bounds = [0.0] * 6
                    node.GetRASBounds(bounds)
                    boundsList.append(bounds)
            elif entry["kind"] == "volume_rendering":
                bounds = [0.0] * 6
                entry["node"].GetRASBounds(bounds)
                boundsList.append(bounds)
            else:
                for segmentId in entry["segmentIds"]:
                    try:
                        boundsList.append(
                            self.logic.getSegmentationSegmentBoundsWorld(
                                entry.get("segmentationNode")
                                or self._parameterNode.teethSegmentation,
                                segmentId,
                            )
                        )
                    except ValueError:
                        continue
        finiteBounds = [
            tuple(float(value) for value in bounds)
            for bounds in boundsList
            if len(bounds) == 6
            and all(math.isfinite(float(value)) for value in bounds)
            and all(bounds[2 * axis + 1] > bounds[2 * axis] for axis in range(3))
        ]
        if not finiteBounds:
            self.ui.workflowViewStatusLabel.text = _(
                "No visible workflow geometry is available to frame."
            )
            self.ui.workflowViewStatusLabel.styleSheet = "color: #b36b00;"
            return
        combined = tuple(
            min(bounds[axis] for bounds in finiteBounds)
            if axis % 2 == 0
            else max(bounds[axis] for bounds in finiteBounds)
            for axis in range(6)
        )
        self._frameRasBoundsInViews(combined)
        self.ui.workflowViewStatusLabel.text = _(
            "Framed the currently visible workflow elements."
        )
        self.ui.workflowViewStatusLabel.styleSheet = "color: #207227;"

    def _hideLegacyPost5BControls(self) -> None:
        """Keep old scene fields readable while removing their superseded UI path."""

        obsoleteWidgetNames = (
            "templateGuideVisibilityGroupBox",
            "templateShellRoiLabel",
            "templateShellRoiSelector",
            "createTemplateShellRoiButton",
            "deleteTemplateShellRoiButton",
            "templateChannelDiameterLabel",
            "templateChannelDiameterSpinBox",
            "researchTemplateShellModelLabel",
            "researchTemplateShellModelSelector",
            "researchTemplateSleeveModelLabel",
            "researchTemplateSleeveModelSelector",
            "shellRoiVisibilityCheckBox",
            "shellModelVisibilityCheckBox",
            "sleeveModelVisibilityCheckBox",
            "generateResearchTemplateButton",
            "deleteResearchTemplateButton",
            "templateGuideStatusLabel",
            "templateGuideSafetyLabel",
            "templateFinalizationDescriptionLabel",
            "templateFinalizationLineageLabel",
            "templateFinalizationSourceLabel",
            "templateFinalizationSourceValueLabel",
            "templateFinalizationModeLabel",
            "templateFinalizationModeComboBox",
            "templateFinalizationKeepRegionLabel",
            "templateFinalizationKeepRegionComboBox",
            "templateTrimPlaneLabel",
            "templateTrimPlaneSelector",
            "templateTrimCurveLabel",
            "templateTrimCurveSelector",
            "finalizedTemplateShellModelLabel",
            "finalizedTemplateShellModelSelector",
            "templateFinalizationCameraFrameLabel",
            "templateFinalizationViewLockedCheckBox",
            "templateFinalizationYawLockedCheckBox",
            "continueTemplateFinalizationButton",
            "restoreTemplateFinalizationViewButton",
            "createTemplateTrimPlaneButton",
            "placeTemplateTrimCurveButton",
            "applyTemplateFinalizationButton",
            "openDynamicModelerButton",
            "deleteTemplateFinalizationButton",
            "exportResearchTemplateButton",
            "templateFinalizationStatusLabel",
            "templateFinalizationSafetyLabel",
        )
        for widgetName in obsoleteWidgetNames:
            widget = getattr(self.ui, widgetName, None)
            if widget:
                widget.visible = False

    def onWorkflowStageChanged(self, index: int) -> None:
        if self._updatingWorkflowNavigationUI:
            return
        self._setWorkflowStage(index)

    def onPreviousWorkflowStage(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(self.ui.workflowStageComboBox.currentIndex - 1)

    def onNextWorkflowStage(self, checked: bool = False) -> None:
        del checked
        self._setWorkflowStage(self.ui.workflowStageComboBox.currentIndex + 1)

    def _setWorkflowStage(self, index: int, ensureVisible: bool = True) -> None:
        entries = self._workflowStageEntries()
        if not entries:
            return
        index = max(0, min(int(index), len(entries) - 1))
        previousIndex = int(self.ui.workflowStageComboBox.currentIndex)
        stageChanged = index != previousIndex
        self._updatingWorkflowNavigationUI = True
        try:
            self.ui.workflowStageComboBox.currentIndex = index
            activeSection = entries[index][1]
            for section in {entry[1] for entry in entries}:
                isActive = section is activeSection
                section.visible = isActive
                section.collapsed = not isActive
            self._configureTemplateModelingStage(index)
            self._updateStageExclusiveInteractionLocks(index)
            self.ui.stepTitleLabel.text = entries[index][0].upper()
        finally:
            self._updatingWorkflowNavigationUI = False
        self._updateTrajectoryPlacementModeControls()
        self._updateWorkflowNavigationButtons()
        self._activateWorkflowViewStage(index, stageChanged=stageChanged)
        self._updateWorkflowNavigationRecommendation()
        if self._applicationShell and self._applicationShell.active:
            self._applicationShell.syncStage(
                index,
                self._recommendedWorkflowStageIndex(),
            )
        self._updateRobotKeyboardShortcutState()
        if index == len(entries) - 1:
            # ROS status nodes are intentionally lazy: entering Step 6 is the
            # lifecycle boundary that may create them.
            self._updateRos2MotionControlStatus()
        if ensureVisible:
            qt.QTimer.singleShot(
                0,
                lambda section=entries[index][1]: self._ensureWorkflowSectionVisible(
                    section
                ),
            )

    def _onWorkflowSectionCollapsed(self, section, collapsed: bool) -> None:
        if self._updatingWorkflowNavigationUI:
            return
        currentIndex = int(self.ui.workflowStageComboBox.currentIndex)
        if self._workflowStageEntries()[currentIndex][1] is not section or not collapsed:
            return
        # A wizard stage is not a free accordion. Keep the one active section
        # open so the task area can never become an empty stack of headers.
        self._updatingWorkflowNavigationUI = True
        try:
            section.collapsed = False
        finally:
            self._updatingWorkflowNavigationUI = False

    def _configureTemplateModelingStage(self, stageIndex: int) -> None:
        """Expose support selection in 4B and surface refinement in 5A."""

        if not hasattr(self, "ui"):
            return
        selectionStage = stageIndex == 5
        surfaceStage = stageIndex == 7
        if not (selectionStage or surfaceStage):
            return
        self.ui.templateModelingCollapsibleButton.text = (
            _("Step 4B — Select Support Teeth and Build Anatomy Draft")
            if selectionStage
            else _("Step 5A — Define the Visible Support Surface")
        )
        self.ui.templateModelingDescriptionLabel.text = (
            _(
                "Select same-jaw support teeth and create the complete, world-RAS "
                "anatomy draft used by Step 4C collision screening. Source masks "
                "are never modified."
            )
            if selectionStage
            else _(
                "Refine the already selected support anatomy to the clinically "
                "visible erupted contact surface using the automatic plane or an "
                "editable boundary."
            )
        )
        selectionWidgets = (
            self.ui.templateTargetToothTitleLabel,
            self.ui.templateTargetToothValueLabel,
            self._templateSupportArchWidget,
            self.ui.draftTemplateSupportModelTitleLabel,
            self.ui.draftTemplateSupportModelSelector,
            self.ui.reviewSegmentationForTemplateButton,
            self.ui.createDraftTemplateSupportModelButton,
            self.ui.deleteDraftTemplateSupportModelButton,
        )
        surfaceWidgets = (
            self.ui.templateSupportBoundaryCurveLabel,
            self.ui.templateSupportBoundaryCurveSelector,
            self.ui.templateSupportSelectionModeLabel,
            self.ui.templateSupportDirectionValueLabel,
            self.ui.flipTemplateSupportDirectionButton,
            self.ui.templateSupportCurveSamplingSpacingLabel,
            self.ui.templateSupportCurveSamplingSpacingSpinBox,
            self.ui.templateTerminalSupportCoverageLabel,
            self.ui.templateTerminalSupportCoverageSpinBox,
            self.ui.visibleTemplateSupportModelLabel,
            self.ui.visibleTemplateSupportModelSelector,
            self.ui.templateSupportBoundaryPlaneLabel,
            self.ui.templateSupportBoundaryPlaneSelector,
            self.ui.templateSupportPlaneDepthLabel,
            self.ui.templateSupportPlaneDepthSpinBox,
            self.ui.templateSupportCrownCapLabel,
            self.ui.templateSupportCrownCapSpinBox,
            self.ui.createTemplateSupportPlaneButton,
            self.ui.generateTemplateSupportBoundaryFromPlaneButton,
            self.ui.createTemplateSupportBoundaryButton,
            self.ui.generateVisibleTemplateSupportModelButton,
            self.ui.deleteTemplateSupportSelectionButton,
            self.ui.templateSupportSurfaceStatusLabel,
        )
        for widget in selectionWidgets:
            widget.visible = selectionStage
        # This hidden QListWidget is only the persistent adapter behind the
        # Step 4B arch map. It has been removed from the form layout and must
        # remain hidden in every stage.
        self.ui.templateSupportTeethListWidget.visible = False
        self.ui.templateSupportTeethTitleLabel.visible = False
        self._templateSupportPackageWidget.visible = surfaceStage
        for widget in surfaceWidgets:
            if widget:
                widget.visible = surfaceStage
        self.ui.templateSupportViewControlsGroupBox.visible = True

    def onReturnToStep4BSupportSelection(self, checked: bool = False) -> None:
        """Navigate from the Step 5A consumer view to the Step 4B owner."""

        del checked
        self._setWorkflowStage(5)

    def _ensureWorkflowSectionVisible(self, section) -> None:
        if not self._workflowContentScrollArea:
            return
        self._workflowContentScrollArea.ensureWidgetVisible(section, 0, 0)
        scrollBar = self._workflowContentScrollArea.verticalScrollBar()
        scrollBar.setValue(max(0, int(section.y) - 4))

    def _updateWorkflowNavigationButtons(self) -> None:
        count = len(self._workflowStageEntries())
        index = int(self.ui.workflowStageComboBox.currentIndex)
        self.ui.previousWorkflowStageButton.enabled = index > 0
        self.ui.nextWorkflowStageButton.enabled = 0 <= index < count - 1

    def _recommendedWorkflowStageIndex(self) -> int:
        if not self._parameterNode:
            return 0
        if not self._parameterNode.inputVolume:
            # A brand-new empty scene must open on the Case stage so the
            # operator can deliberately create a de-identified case or open a
            # saved scene. Once a case label exists, imaging is the next
            # recommendation, but the navigator never skips Case at first
            # initialization merely because no volume is loaded yet.
            return 1 if self._parameterNode.caseName.strip() else 0
        segmentationNode = self._parameterNode.teethSegmentation
        if not segmentationNode:
            return 2
        if self.logic.getSegmentationReviewState(segmentationNode) != "Reviewed":
            return 3
        trajectoryNode = self._parameterNode.trajectoryLine
        if not trajectoryNode or trajectoryNode.GetNumberOfDefinedControlPoints() < 2:
            return 4
        if not trajectoryNode.GetLocked():
            return 4
        supportModel = self._parameterNode.draftTemplateSupportModel
        if (
            not supportModel
            or supportModel.GetAttribute("DENTOBOT.GeometryState") != "Current"
        ):
            return 5
        dockingModel = self._parameterNode.targetDockingAssemblyModel
        if (
            not dockingModel
            or dockingModel.GetAttribute("DENTOBOT.GeometryState") != "Current"
            or dockingModel.GetAttribute("DENTOBOT.OrientationState") != "Confirmed"
        ):
            return 6
        if not self._parameterNode.visibleTemplateSupportModel:
            return 7
        if not self._parameterNode.finalPrintableTemplateModel:
            return 8
        return 9

    def _updateWorkflowNavigationRecommendation(self) -> None:
        recommendedIndex = self._recommendedWorkflowStageIndex()
        entries = self._workflowStageEntries()
        recommendation = _("Recommended next: %1").replace(
            "%1",
            entries[recommendedIndex][0],
        )
        self.ui.workflowStageStatusLabel.text = "●"
        self.ui.workflowStageStatusLabel.toolTip = recommendation
        self.ui.workflowStageStatusLabel.accessibleName = recommendation
        currentIndex = int(self.ui.workflowStageComboBox.currentIndex)
        indicatorColor = "#207227" if currentIndex == recommendedIndex else "#1f5f99"
        self.ui.workflowStageStatusLabel.styleSheet = (
            f"color: {indicatorColor}; font-size: 15px;"
        )
        self.ui.workflowStageComboBox.toolTip = _(
            "Jump to one workflow stage. %1"
        ).replace("%1", recommendation)
        if not self._workflowNavigationInitializedFromScene:
            self._workflowNavigationInitializedFromScene = True
            self._setWorkflowStage(recommendedIndex, ensureVisible=False)
        elif self._applicationShell and self._applicationShell.active:
            self._applicationShell.syncStage(currentIndex, recommendedIndex)
