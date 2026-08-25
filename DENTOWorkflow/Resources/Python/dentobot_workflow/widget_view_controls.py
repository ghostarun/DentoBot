"""Extracted view element controls methods; public APIs remain on ViewerWidgetMixin."""

from __future__ import annotations

from .runtime import *


class ViewControlsWidgetMixin:
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
