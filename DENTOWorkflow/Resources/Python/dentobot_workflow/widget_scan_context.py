"""Source-paired inspection, independent of the committed planning inputs."""

from .runtime import *


class ScanContextWidgetMixin:
    @staticmethod
    def _displayViewNodeIds(displayNode):
        if not displayNode or not hasattr(displayNode, "GetViewNodeIDs"):
            return None
        values = displayNode.GetViewNodeIDs()
        if values is None:
            return ()
        if hasattr(values, "GetNumberOfValues"):
            return tuple(values.GetValue(index) for index in range(values.GetNumberOfValues()))
        try:
            return tuple(values)
        except TypeError:
            return ()

    @staticmethod
    def _setSegmentationViewNodes(displayNode, viewNodeIds):
        if not displayNode or not hasattr(displayNode, "SetViewNodeIDs"):
            return
        viewIds = vtk.vtkStringArray()
        for viewNodeId in viewNodeIds:
            viewIds.InsertNextValue(str(viewNodeId))
        try:
            displayNode.SetViewNodeIDs(viewIds)
        except (AttributeError, TypeError):
            # Older Slicer builds can expose the getter without a writable
            # view-ID setter; comparison still works through its backgrounds.
            return

    @staticmethod
    def _sliceComparisonViews(layoutManager):
        views = []
        for name in ("Red", "Green", "Yellow"):
            sliceWidget = layoutManager.sliceWidget(name)
            if sliceWidget:
                views.append(
                    (
                        sliceWidget.mrmlSliceNode(),
                        sliceWidget.mrmlSliceCompositeNode(),
                    )
                )
        return views

    def _scanRuns(self, volume):
        return [node for node in self._dentobotTeethSegmentationNodes()
                if node.GetNodeReference(self.logic.SOURCE_VOLUME_REFERENCE_ROLE) == volume]

    def _inspectionActive(self):
        return bool(self._parameterNode and
                    int(self.ui.workflowStageComboBox.currentIndex) <= 3)

    def _setupScanContext(self):
        self._selectingInspection = False
        self._scanSliceStates = {}
        self._comparisonState = None
        self.ui.inputVolumeSelector.addAttribute(
            "vtkMRMLScalarVolumeNode", "DENTOBOT.CaseScan", "true"
        )
        self.ui.reviewSegmentationSelector.addAttribute(
            "vtkMRMLSegmentationNode", "DENTOBOT.BridgeOperation", "segment-teeth"
        )
        self._scanHeader = qt.QFrame(self._uiWidget)
        form = qt.QFormLayout(self._scanHeader)
        self._scanCaseLabel = qt.QLabel()
        form.addRow(self._scanCaseLabel)
        for label, selector, callback in (
            (_("Scan"), self.ui.inputVolumeSelector, self._renameInspectedScan),
            (_("Result"), self.ui.reviewSegmentationSelector, self.onRenameSelectedSegmentation),
        ):
            row = qt.QWidget()
            layout = qt.QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            selector.setParent(row)
            layout.addWidget(selector, 1)
            rename = qt.QPushButton(_("Rename"))
            rename.connect("clicked(bool)", callback)
            layout.addWidget(rename)
            form.addRow(label, row)
        root = self._uiWidget.layout()
        root.insertWidget(root.indexOf(self._workflowContentScrollArea), self._scanHeader)
        self._scanFooter = qt.QFrame(self._uiWidget)
        footer = qt.QVBoxLayout(self._scanFooter)
        self._scanHint = qt.QLabel()
        self._scanHint.wordWrap = True
        footer.addWidget(self._scanHint)
        buttons = qt.QHBoxLayout()
        back = qt.QPushButton(_("Back"))
        back.connect("clicked(bool)", self.onPreviousWorkflowStage)
        self._scanContinue = qt.QPushButton()
        self._scanContinue.connect("clicked(bool)", self._continueInspection)
        buttons.addWidget(back)
        buttons.addWidget(self._scanContinue, 1)
        footer.addLayout(buttons)
        root.addWidget(self._scanFooter)
        # The original selector labels are now represented in the fixed header.
        self.ui.inputVolumeLabel.hide()
        self.ui.showSelectedSegmentationOnlyButton.hide()
        self.ui.showAllSegmentationRunsButton.hide()
        self.ui.renameSelectedSegmentationButton.hide()
        self.ui.showAllSegmentsButton.text = _("Show all labels in this run")
        self.ui.hideAllSegmentsButton.text = _("Hide all labels in this run")
        comparisonRow = qt.QWidget(self.ui.segmentationReviewCollapsibleButton)
        comparisonLayout = qt.QHBoxLayout(comparisonRow)
        comparisonLayout.setContentsMargins(0, 0, 0, 0)
        self._compareButton = qt.QPushButton(_("Compare…"), comparisonRow)
        self._compareButton.connect("clicked(bool)", self.onEnterComparison)
        self._exitCompareButton = qt.QPushButton(_("Exit Comparison"), comparisonRow)
        self._exitCompareButton.connect("clicked(bool)", self.exitComparison)
        self._usePlanningButton = qt.QPushButton(_("Use for Planning → Step 4"), comparisonRow)
        self._usePlanningButton.connect("clicked(bool)", self._continueInspection)
        comparisonLayout.addWidget(self._compareButton)
        comparisonLayout.addWidget(self._exitCompareButton)
        comparisonLayout.addWidget(self._usePlanningButton)
        self.ui.segmentationReviewCollapsibleButton.layout().insertWidget(2, comparisonRow)
        self._syncScanContext()

    def _renameInspectedScan(self, checked=False):
        node = self._parameterNode.inspectedVolume
        if node:
            name = qt.QInputDialog.getText(slicer.util.mainWindow(), _("Rename scan"),
                                         _("Research label:"), qt.QLineEdit.Normal, node.GetName())
            if name and str(name).strip():
                node.SetName(str(name).strip())

    def _syncScanContext(self):
        if not hasattr(self, "_scanHeader") or not self._parameterNode:
            return
        stage = int(self.ui.workflowStageComboBox.currentIndex)
        active = stage <= 3
        self._scanHeader.visible = active
        self._scanFooter.visible = active
        self._scanCaseLabel.text = _("Case: %1").replace("%1", self._parameterNode.caseName or _("Unnamed research case"))
        volume = self._parameterNode.inspectedVolume
        run = self._parameterNode.inspectedSegmentation
        self._scanContinue.text = (
            _("Choose Scan"), _("Continue to Segmentation"),
            _("Review Selected Run"), _("Use for Planning → Step 4")
        )[min(stage, 3)]
        self._scanContinue.enabled = (
            bool(volume)
            if stage == 0
            else bool(volume and (stage == 1 or run))
        )
        if hasattr(self, "_compareButton"):
            self._compareButton.visible = stage == 3 and run is not None and self._comparisonState is None
            self._exitCompareButton.visible = stage == 3 and self._comparisonState is not None
            self._usePlanningButton.visible = stage == 3 and self._comparisonState is None
            self._usePlanningButton.enabled = bool(run)
        if not volume:
            self._scanHint.text = _("Select a source scan to begin.")
        else:
            image = volume.GetImageData()
            geometry = ""
            if image:
                dims = image.GetDimensions()
                spacing = volume.GetSpacing()
                geometry = _(" · %1×%2×%3 voxels · %4/%5/%6 mm").replace("%1", str(dims[0])).replace("%2", str(dims[1])).replace("%3", str(dims[2])).replace("%4", f"{spacing[0]:.3g}").replace("%5", f"{spacing[1]:.3g}").replace("%6", f"{spacing[2]:.3g}")
            self._scanHint.text = (
                _("%1%2 · No segmentation yet. Run segmentation for this scan in Step 2.").replace("%1", volume.GetName()).replace("%2", geometry)
                if not run else
                _("%1%2 · %3 / %4 · %5").replace("%1", volume.GetName()).replace("%2", geometry).replace("%3", run.GetName()).replace("%4", self.logic.getSegmentationReviewState(run)).replace("%5", _("inspection only; planning remains unchanged"))
            )

    def _continueInspection(self, checked=False):
        stage = int(self.ui.workflowStageComboBox.currentIndex)
        if stage == 3:
            if not self.commitInspectionContextForPlanning():
                return
        self._setWorkflowStage(min(stage + 1, 4))

    def selectInspectionContext(self, volume, segmentation=None):
        if not self._parameterNode or getattr(self, "_selectingInspection", False):
            return
        if segmentation and self.logic.getSegmentationSourceVolume(segmentation) != volume:
            raise ValueError(_("This segmentation belongs to another source scan."))
        if volume and segmentation is None:
            runs = self._scanRuns(volume)
            remembered = volume.GetNodeReference("DENTOBOT.InspectedRun")
            segmentation = remembered if remembered in runs else (runs[-1] if runs else None)
        self._selectingInspection = True
        oldUpdating = self._updatingFromParameterNode
        self._updatingFromParameterNode = True
        try:
            previous = self._parameterNode.inspectedVolume
            if previous != volume:
                self._workflowViewPriorState = None
            modify = self._parameterNode.StartModify()
            try:
                self._parameterNode.inspectedVolume = volume
                self._parameterNode.inspectedSegmentation = segmentation
                if volume and segmentation:
                    volume.SetNodeReferenceID("DENTOBOT.InspectedRun", segmentation.GetID())
                if volume:
                    volume.SetAttribute("DENTOBOT.CaseScan", "true")
            finally:
                self._parameterNode.EndModify(modify)
            # qMRMLNodeComboBox filters by a transient source key, never by label.
            for run in self._dentobotTeethSegmentationNodes():
                source = run.GetNodeReference(self.logic.SOURCE_VOLUME_REFERENCE_ROLE)
                run.SetAttribute("DENTOBOT.InspectionSourceKey", source.GetID() if source else "unassigned")
            selector = self.ui.reviewSegmentationSelector
            selector.blockSignals(True)
            try:
                selector.removeAttribute("vtkMRMLSegmentationNode", "DENTOBOT.InspectionSourceKey")
                selector.addAttribute("vtkMRMLSegmentationNode", "DENTOBOT.InspectionSourceKey", volume.GetID() if volume else "unassigned")
                selector.setCurrentNode(segmentation)
            finally:
                selector.blockSignals(False)
            self.ui.inputVolumeSelector.blockSignals(True)
            self.ui.inputVolumeSelector.setCurrentNode(volume)
            self.ui.inputVolumeSelector.blockSignals(False)
            self._bindSegmentationReviewNode(segmentation)
            self._updateSegmentationReview()
            if self._inspectionActive():
                self._displayInspectionContext(fit=previous != volume)
            self._updateBackendControls()
            self._syncScanContext()
        finally:
            self._updatingFromParameterNode = oldUpdating
            self._selectingInspection = False

    def _displayInspectionContext(self, fit=False):
        if not self._inspectionActive():
            return
        volume = self._parameterNode.inspectedVolume
        selected = self._parameterNode.inspectedSegmentation
        slicer.util.setSliceViewerLayers(background=volume, foreground=None, label=None, fit=fit)
        for run in self._dentobotTeethSegmentationNodes():
            run.CreateDefaultDisplayNodes()
            run.GetDisplayNode().SetVisibility(run == selected)

    def _comparisonCandidates(self):
        selected = self._parameterNode.inspectedSegmentation
        candidates = []
        for run in self._dentobotTeethSegmentationNodes():
            if run == selected:
                continue
            source = run.GetNodeReference(self.logic.SOURCE_VOLUME_REFERENCE_ROLE)
            if source:
                candidates.append((source, run))
        return candidates

    def onEnterComparison(self, checked=False):
        del checked
        candidates = self._comparisonCandidates()
        if not candidates:
            slicer.util.infoDisplay(_("No other DENTOBOT segmentation run is available for comparison."))
            return
        labels = [f"{source.GetName()} / {run.GetName()}" for source, run in candidates]
        choice, accepted = qt.QInputDialog.getItem(
            slicer.util.mainWindow(), _("Compare segmentation runs"),
            _("Reference run:"), labels, 0, False
        )
        if accepted:
            index = labels.index(str(choice))
            self.enterComparison(*candidates[index])

    def enterComparison(self, referenceVolume, referenceSegmentation):
        if self._comparisonState or not self._parameterNode:
            return
        composites = list(slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode"))
        layoutManager = slicer.app.layoutManager()
        self._comparisonState = {
            "layout": layoutManager.layout,
            "composites": [
                (
                    node,
                    node.GetBackgroundVolumeID(),
                    node.GetForegroundVolumeID(),
                    node.GetLabelVolumeID(),
                    bool(node.GetLinkedControl()),
                    bool(node.GetHotLinkedControl()),
                )
                for node in composites
            ],
            "visibility": [(node, node.GetDisplayNode().GetVisibility(), node.GetDisplayNode().GetVisibility2D(), node.GetDisplayNode().GetVisibility3D(), node.GetDisplayNode().GetOpacity3D()) for node in self._dentobotTeethSegmentationNodes()],
            "viewNodeIDs": [
                (
                    node,
                    self._displayViewNodeIds(node.GetDisplayNode()),
                )
                for node in self._dentobotTeethSegmentationNodes()
            ],
        }
        activeVolume = self._parameterNode.inspectedVolume
        activeRun = self._parameterNode.inspectedSegmentation
        for run in self._dentobotTeethSegmentationNodes():
            run.CreateDefaultDisplayNodes()
            run.GetDisplayNode().SetVisibility(run in (activeRun, referenceSegmentation))
        if referenceVolume == activeVolume:
            slicer.util.setSliceViewerLayers(background=activeVolume, foreground=None, label=None, fit=False)
            self.ui.segmentationReviewStatusLabel.text = _(
                "Comparison: two runs from %1 are visible together. The selected run remains authoritative."
            ).replace("%1", activeVolume.GetName())
        else:
            sideBySide = getattr(
                slicer.vtkMRMLLayoutNode,
                "SlicerLayoutSideBySideView",
                slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView,
            )
            layoutManager.setLayout(sideBySide)
            # Changing layout may recreate the slice composite nodes; always
            # bind the newly materialized viewers, not the pre-layout nodes.
            comparisonComposites = list(
                slicer.util.getNodesByClass("vtkMRMLSliceCompositeNode")
            )
            for composite in comparisonComposites:
                composite.SetLinkedControl(False)
                composite.SetHotLinkedControl(False)
            if len(comparisonComposites) >= 2:
                comparisonComposites[0].SetBackgroundVolumeID(activeVolume.GetID())
                comparisonComposites[0].SetForegroundVolumeID(None)
                comparisonComposites[0].SetLabelVolumeID(None)
                comparisonComposites[1].SetBackgroundVolumeID(referenceVolume.GetID())
                comparisonComposites[1].SetForegroundVolumeID(None)
                comparisonComposites[1].SetLabelVolumeID(None)
            comparisonViews = self._sliceComparisonViews(layoutManager)
            if len(comparisonViews) >= 2:
                self._setSegmentationViewNodes(
                    activeRun.GetDisplayNode(),
                    [comparisonViews[0][0].GetID()],
                )
                self._setSegmentationViewNodes(
                    referenceSegmentation.GetDisplayNode(),
                    [comparisonViews[1][0].GetID()],
                )
            self.ui.segmentationReviewStatusLabel.text = _(
                "Comparison: %1 and %2 are shown in separate slice viewers. The selected run remains authoritative."
            ).replace("%1", activeVolume.GetName()).replace("%2", referenceVolume.GetName())
        self._syncScanContext()

    def exitComparison(self, checked=False):
        del checked
        if not self._comparisonState:
            return
        layoutManager = slicer.app.layoutManager()
        for node, background, foreground, label, linked, hotLinked in self._comparisonState["composites"]:
            node.SetBackgroundVolumeID(background)
            node.SetForegroundVolumeID(foreground)
            node.SetLabelVolumeID(label)
            node.SetLinkedControl(linked)
            node.SetHotLinkedControl(hotLinked)
        for node, visible, visible2d, visible3d, opacity in self._comparisonState["visibility"]:
            node.CreateDefaultDisplayNodes()
            display = node.GetDisplayNode()
            display.SetVisibility(visible)
            display.SetVisibility2D(visible2d)
            display.SetVisibility3D(visible3d)
            display.SetOpacity3D(opacity)
        for node, viewNodeIds in self._comparisonState["viewNodeIDs"]:
            if viewNodeIds is not None:
                self._setSegmentationViewNodes(node.GetDisplayNode(), viewNodeIds)
        layoutManager.setLayout(self._comparisonState["layout"])
        self._comparisonState = None
        self._displayInspectionContext()
        self.ui.segmentationReviewStatusLabel.text = _("Comparison closed. The selected scan and run are active again.")
        self._syncScanContext()

    def commitInspectionContextForPlanning(self):
        parameter = self._parameterNode
        run = parameter.inspectedSegmentation
        if not run or self.logic.getSegmentationReviewState(run) != "Reviewed":
            slicer.util.infoDisplay(_("Complete the segmentation review before using this result for planning."))
            return False
        if self.logic.getSegmentationSourceVolume(run) != parameter.inspectedVolume:
            raise ValueError(_("The inspected scan and result do not match."))
        changed = parameter.teethSegmentation != run
        if changed and any((parameter.trajectoryLine, parameter.finalPrintableTemplateModel, parameter.targetToothSegmentId)):
            if not slicer.util.confirmYesNoDisplay(_("Use this scan/result for planning? Existing Step 4 trajectory, Step 5 template and Step 6 evidence will require revalidation. Browsing alone preserves them.")):
                return False
        self._commitPlanningSegmentationSelection(run)
        if parameter.teethSegmentation != run:
            return False
        parameter.inputVolume = parameter.inspectedVolume
        return True
